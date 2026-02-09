# app.py - Streamlit Blood Analysis App with Peripheral Blood Smear Integration

import streamlit as st
import PyPDF2
from PIL import Image
import pytesseract
import re
import io
import pandas as pd

# Normal ranges (adult general; adjust as needed)
NORMAL_RANGES = {
    'RBC': {'min': 4.5, 'max': 5.9, 'unit': 'x10^12/L', 'desc': 'Red Blood Cell Count'},
    'Hemoglobin': {'min': 13.5, 'max': 17.5, 'unit': 'g/dL', 'desc': 'Hemoglobin (Hb)'},
    'Hematocrit': {'min': 41, 'max': 53, 'unit': '%', 'desc': 'Hematocrit (HCT)'},
    'MCV': {'min': 80, 'max': 100, 'unit': 'fL', 'desc': 'Mean Corpuscular Volume'},
    'MCH': {'min': 27, 'max': 31, 'unit': 'pg', 'desc': 'Mean Corpuscular Hemoglobin'},
    'MCHC': {'min': 32, 'max': 36, 'unit': 'g/dL', 'desc': 'Mean Corpuscular Hemoglobin Concentration'},
    'RDW': {'min': 11.5, 'max': 14.5, 'unit': '%', 'desc': 'Red Cell Distribution Width'},
    'WBC': {'min': 4.5, 'max': 11.0, 'unit': 'x10^9/L', 'desc': 'White Blood Cell Count'},
    'Neutrophils': {'min': 1.8, 'max': 7.7, 'unit': 'x10^9/L', 'desc': 'Neutrophils (Absolute)'},
    'Lymphocytes': {'min': 1.0, 'max': 4.8, 'unit': 'x10^9/L', 'desc': 'Lymphocytes (Absolute)'},
    'Platelets': {'min': 150, 'max': 450, 'unit': 'x10^9/L', 'desc': 'Platelet Count'},
    # Add more as needed
}

# Collection & Storage Advice (from document)
COLLECTION_ADVICE = """
**Collection & Storage Summary (from document):**
- Use trained phlebotomist; EDTA (purple top) or citrate (blue top) tube.
- Avoid hemolysis (tight tourniquet/small needle), under/overfilling, IV proximal collection.
- EDTA can cause platelet clumping → pseudothrombocytopenia (review smear edge or repeat with citrate).
- Room temp <24h; refrigerate <72h; avoid freeze/heat.
- >72h: spurious ↑ MCV/MPV, altered WBC %.
- Films within 8h to avoid pyknosis/artifacts.
"""

# Common PBS findings (document-inspired + standard hematology)
PBS_GUIDE = """
**Peripheral Blood Smear (PBS) Key Features (from document & standard eval):**
- **Anemia (low RBC/Hb/HCT):** Anisocytosis/poikilocytosis, microcytes (iron def/thalassemia), macrocytes (B12/folate def), spherocytes (hemolysis/hereditary), schistocytes (MAHA), target cells (thalassemia/liver), teardrop (myelofibrosis).
- **High RDW/abnormal histogram:** Left shoulder → small cells (microspherocytes/schistocytes/platelet clumps misread as RBCs); Right shoulder → large cells (reticulocytes/agglutination).
- **Thrombocytopenia:** True low platelets vs. clumps (EDTA artifact); giant platelets in some congenital disorders.
- **Neutropenia/Neutrophilia:** Left shift/immature forms (infection/malignancy); toxic granulation/Döhle bodies (infection).
- **General artifacts:** Crenated RBCs (old/heat), fragments (heat/hemolysis), pyknotic WBCs (old sample).
- Always review for blasts, abnormal WBC morphology, or inclusions.
"""

# Functions (parse, quality, analyze) - same as before, with PBS triggers added in analyze

def extract_text_from_pdf(file):
    pdf_reader = PyPDF2.PdfReader(file)
    text = ""
    for page in pdf_reader.pages:
        text += page.extract_text() + "\n"
    return text

def extract_text_from_image(file):
    image = Image.open(file)
    text = pytesseract.image_to_string(image)
    return text

def parse_cbc_values(text):
    patterns = {
        'RBC': r'(?:RBC|Red\s*Blood\s*Cell\s*Count)[\s:=]*([\d.,]+)',
        'Hemoglobin': r'(?:Hemoglobin|Hb|HGB)[\s:=]*([\d.,]+)',
        'Hematocrit': r'(?:Hematocrit|HCT|PCV)[\s:=]*([\d.,]+)',
        'MCV': r'MCV[\s:=]*([\d.,]+)',
        'RDW': r'RDW[\s:=]*([\d.,]+)',
        'WBC': r'(?:WBC|White\s*Blood\s*Cell\s*Count)[\s:=]*([\d.,]+)',
        'Neutrophils': r'(?:Neutrophils|NEU)[\s:=]*([\d.,]+)',
        'Platelets': r'(?:Platelets|PLT)[\s:=]*([\d.,]+)',
    }
    values = {}
    text = text.replace(',', '.').replace('^', '').replace('x10', 'e')
    for key, pattern in patterns.items():
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            captured = match.group(1).strip()
            cleaned = re.sub(r'[^0-9.]', '', captured)
            if cleaned:
                try:
                    values[key] = float(cleaned)
                except ValueError:
                    pass
    return values

def assess_sample_quality(values, sample_age_hours, storage_temp):
    issues = []
    if sample_age_hours > 72:
        issues.append("Sample >72h → spurious ↑ MCV/MPV; smear may show pyknotic cells/crenated RBCs.")
    if storage_temp == "Frozen":
        issues.append("Freezing → lysis → inaccurate; smear useless.")
    if storage_temp == "Heated":
        issues.append("Heat → RBC fragments (schistocyte-like) → misread as platelets on autoanalyzer.")
    if 'Platelets' in values and values['Platelets'] < NORMAL_RANGES['Platelets']['min']:
        issues.append("Low platelets → check smear for clumping (EDTA pseudothrombocytopenia).")
    return issues

def analyze_values(values):
    analysis = []
    pbs_recommend = False
    pbs_reasons = []

    for param, val in values.items():
        if param in NORMAL_RANGES:
            rng = NORMAL_RANGES[param]
            status = "Normal"
            suggestion = "Within normal range."
            if val < rng['min']:
                status = "Low"
                if param in ['RBC', 'Hemoglobin', 'Hematocrit']:
                    suggestion = "Counts too low (RBCs) – See \"Approach to the child with anemia\" and \"Diagnostic approach to anemia in adults\"."
                    pbs_recommend = True
                    pbs_reasons.append("Anemia evaluation: Look for anisopoikilocytosis, micro/macrocytic features, schistocytes/spherocytes.")
                elif param == 'Platelets':
                    suggestion = "Counts too low (Platelets) – See \"Approach to the child with unexplained thrombocytopenia\" and \"Diagnostic approach to thrombocytopenia in adults\"."
                    pbs_recommend = True
                    pbs_reasons.append("Thrombocytopenia: Check for true low vs. clumps (pseudothrombocytopenia from EDTA).")
                elif param == 'WBC':
                    suggestion = "Counts too low (WBCs) – See \"Evaluation of neutropenia in children and adolescents\" and \"Approach to the adult with unexplained neutropenia\"."
                    pbs_recommend = True
                    pbs_reasons.append("Neutropenia: Assess granulocyte morphology, left shift absence.")
                elif param == 'Neutrophils':
                    suggestion = "Neutropenia – See neutropenia approaches."
                    pbs_recommend = True
            elif val > rng['max']:
                status = "High"
                if param in ['RBC', 'Hemoglobin', 'Hematocrit']:
                    suggestion = "Counts too high (RBCs) – See \"Diagnostic approach to the patient with erythrocytosis/polycythemia\"."
                    pbs_recommend = True
                    pbs_reasons.append("Polycythemia: Smear often normocytic/normochromic; exclude secondary causes.")
                elif param == 'Platelets':
                    suggestion = "Counts too high (Platelets) – See \"Approach to the patient with thrombocytosis\"."
                elif param == 'WBC':
                    suggestion = "Counts too high (WBCs) – See \"Approach to the patient with neutrophilia\"."
                    pbs_recommend = True
                    pbs_reasons.append("Neutrophilia: Look for left shift, toxic changes, immature forms.")
            analysis.append({
                'Parameter': rng['desc'],
                'Value': val,
                'Unit': rng['unit'],
                'Status': status,
                'Suggestion': suggestion
            })

    # Rule of Threes
    if all(k in values for k in ['RBC', 'Hemoglobin', 'Hematocrit']):
        rbc, hb, hct = values['RBC'], values['Hemoglobin'], values['Hematocrit']
        if not (abs(3 * rbc - hb) < 1 and abs(3 * hb - hct) < 3):
            analysis.append({
                'Parameter': 'Rule of Threes',
                'Value': 'Violated',
                'Unit': '',
                'Status': 'Abnormal',
                'Suggestion': "Violated – spurious or true condition. Recommend PBS evaluation."
            })
            pbs_recommend = True
            pbs_reasons.append("Rule violation: Check for agglutination, fragments, or other artifacts.")

    # RDW high
    if 'RDW' in values and values['RDW'] > NORMAL_RANGES['RDW']['max']:
        rdw_sugg = "High RDW – anisocytosis; iron def (elevated) vs thalassemia/ACD (normal/slight). See smear for variation."
        analysis.append({'Parameter': 'RDW Interpretation', 'Value': values['RDW'], 'Unit': '%', 'Status': 'Elevated', 'Suggestion': rdw_sugg})
        pbs_recommend = True
        pbs_reasons.append("High RDW: Examine for left/right shoulders on histogram equivalent (small/large cells).")

    # Anemia flag
    if 'Hemoglobin' in values and values['Hemoglobin'] < NORMAL_RANGES['Hemoglobin']['min']:
        anemia_sugg = "Anemia likely. Classify by MCV; see smear for morphology."
        pbs_recommend = True
        pbs_reasons.append("Anemia: Assess RBC shape/size (e.g., hypochromia, targets, sickle).")

    if pbs_recommend:
        analysis.append({
            'Parameter': 'Peripheral Blood Smear Recommendation',
            'Value': 'Strongly Recommended',
            'Unit': '',
            'Status': 'Action Needed',
            'Suggestion': "Review PBS for morphology/clues. See \"Evaluation of the peripheral blood smear\". Reasons: " + "; ".join(pbs_reasons)
        })

    return analysis

# Streamlit UI
st.title("Blood Analysis App with PBS Integration")
st.markdown("CBC analysis + peripheral blood smear recommendations based on document logic.")

with st.expander("Collection/Storage Advice"):
    st.markdown(COLLECTION_ADVICE)

with st.expander("Peripheral Blood Smear Guide"):
    st.markdown(PBS_GUIDE)

option = st.radio("Input Method", ("Upload File", "Manual Input"))

sample_age_hours = st.number_input("Sample Age (hours)", min_value=0.0, value=0.0)
storage_temp = st.selectbox("Storage Temp", ["Room Temperature", "Refrigerated", "Frozen", "Heated"])

values = {}

if option == "Upload File":
    uploaded_file = st.file_uploader("Upload PDF/JPG/JPEG", type=["pdf", "jpg", "jpeg"])
    if uploaded_file:
        if uploaded_file.type == "application/pdf":
            text = extract_text_from_pdf(io.BytesIO(uploaded_file.read()))
        else:
            text = extract_text_from_image(io.BytesIO(uploaded_file.read()))
        if text:
            st.subheader("Extracted Text")
            st.text_area("Text", text, height=200)
            values = parse_cbc_values(text)
            st.subheader("Parsed Values")
            st.json(values)

elif option == "Manual Input":
    st.subheader("Manual Entry")
    for param, info in NORMAL_RANGES.items():
        values[param] = st.number_input(f"{info['desc']} ({info['unit']})", value=0.0, step=0.1)

# PBS user input section
st.subheader("Optional: Observed PBS Findings (Manual Input)")
pbs_findings = {
    'Platelet clumps': st.checkbox("Platelet clumps (possible pseudothrombocytopenia)"),
    'Schistocytes/fragments': st.checkbox("Schistocytes or RBC fragments"),
    'Spherocytes': st.checkbox("Spherocytes"),
    'Target cells': st.checkbox("Target cells"),
    'Teardrop cells': st.checkbox("Teardrop cells"),
    'Left shift': st.checkbox("Immature neutrophils/left shift"),
    'Other (describe)': st.text_input("Other PBS observations")
}

if values:
    st.subheader("Sample Quality Assessment")
    quality_issues = assess_sample_quality(values, sample_age_hours, storage_temp)
    for issue in quality_issues:
        st.warning(issue)

    st.subheader("Analysis & Reporting")
    analysis_list = analyze_values(values)
    if analysis_list:
        df = pd.DataFrame(analysis_list)
        st.dataframe(df)

        abnormals = [row for row in analysis_list if row['Status'] != 'Normal']
        if abnormals:
            st.warning("Abnormalities found – review PBS as recommended.")
        else:
            st.success("Normal ranges.")

# Footer
st.markdown("---")
st.caption("Educational only. PBS review essential for abnormals per document. Not medical advice.")
