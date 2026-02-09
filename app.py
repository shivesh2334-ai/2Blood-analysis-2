# app.py - Updated Streamlit Blood Analysis App based on CBC Document

import streamlit as st
import PyPDF2
from PIL import Image
import pytesseract
import re
import io
import pandas as pd

# Normal ranges (general adult; labs vary; male-leaning where differences exist)
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
    'Monocytes': {'min': 0.2, 'max': 1.0, 'unit': 'x10^9/L', 'desc': 'Monocytes (Absolute)'},
    'Eosinophils': {'min': 0.0, 'max': 0.5, 'unit': 'x10^9/L', 'desc': 'Eosinophils (Absolute)'},
    'Basophils': {'min': 0.0, 'max': 0.2, 'unit': 'x10^9/L', 'desc': 'Basophils (Absolute)'},
    'Platelets': {'min': 150, 'max': 450, 'unit': 'x10^9/L', 'desc': 'Platelet Count'},
    'MPV': {'min': 7.4, 'max': 10.4, 'unit': 'fL', 'desc': 'Mean Platelet Volume'},
    'Reticulocytes': {'min': 0.5, 'max': 1.5, 'unit': '%', 'desc': 'Reticulocyte Count'},
}

# Collection & Storage Advice (directly from document)
COLLECTION_ADVICE = """
**Phlebotomy / Collection:**
- Performed by trained phlebotomist or experienced health care team member.
- Use EDTA (purple top) or sodium citrate (blue top) tube.
- Avoid underfilling/overfilling (affects anticoagulant exposure → spurious results).
- Avoid hemolysis (small gauge needles, tight tourniquets → shearing RBCs → low RBC/Hb).
- Avoid collection proximal to IV line → dilution/spurious low counts.
- EDTA may cause platelet clumping/pseudothrombocytopenia → confirm with smear or citrate tube.

**Storage:**
- Room temperature if analyzed within 24 hours.
- Refrigerate if up to 72 hours.
- Avoid freezing (cell lysis → inaccurate counts).
- Avoid heat exposure (RBC fragmentation → anisocytosis, fragments misread as platelets → high PLT).
- Samples >72 hours: spurious elevated MCV/MPV (cell swelling), altered WBC differentials.
- Prepare blood films within 8 hours (longer storage → pyknotic cells, spurious dysplasia/artifacts).
"""

# Functions
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
        'MCH': r'MCH[\s:=]*([\d.,]+)',
        'MCHC': r'MCHC[\s:=]*([\d.,]+)',
        'RDW': r'RDW[\s:=]*([\d.,]+)',
        'WBC': r'(?:WBC|White\s*Blood\s*Cell\s*Count)[\s:=]*([\d.,]+)',
        'Neutrophils': r'(?:Neutrophils|NEU|Neut|%Neut)[\s:=]*([\d.,]+)',
        'Lymphocytes': r'(?:Lymphocytes|LYM|Lymph|%Lymph)[\s:=]*([\d.,]+)',
        'Monocytes': r'(?:Monocytes|MON|Mono|%Mono)[\s:=]*([\d.,]+)',
        'Eosinophils': r'(?:Eosinophils|EOS|Eos|%Eos)[\s:=]*([\d.,]+)',
        'Basophils': r'(?:Basophils|BAS|Bas|%Bas)[\s:=]*([\d.,]+)',
        'Platelets': r'(?:Platelets|PLT|PLTs)[\s:=]*([\d.,]+)',
        'MPV': r'MPV[\s:=]*([\d.,]+)',
        'Reticulocytes': r'(?:Reticulocytes|RET|retic)[\s:=]*([\d.,]+)',
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
        issues.append("Sample >72 hours old → spurious elevated MCV/MPV from cell swelling (prolonged EDTA).")
    if storage_temp == "Frozen":
        issues.append("Freezing → cell lysis → inaccurate counts.")
    if storage_temp == "Heated":
        issues.append("Heat exposure → RBC fragmentation → anisocytosis, fragments misread as platelets → falsely high PLT.")
    if 'MCV' in values and values['MCV'] > 100:
        issues.append("Elevated MCV → may be artifact (old sample) or true macrocytosis.")
    if 'MPV' in values and values['MPV'] > NORMAL_RANGES['MPV']['max']:
        issues.append("Elevated MPV → prolonged EDTA exposure.")
    if 'Hemoglobin' in values and values['Hemoglobin'] < NORMAL_RANGES['Hemoglobin']['min'] and 'RBC' in values and values['RBC'] < NORMAL_RANGES['RBC']['min']:
        issues.append("Low Hb/RBC → possible hemolysis from collection (shearing).")
    return issues

def analyze_values(values):
    analysis = []
    for param, val in values.items():
        if param in NORMAL_RANGES:
            rng = NORMAL_RANGES[param]
            if val < rng['min']:
                status = "Low"
                if param in ['RBC', 'Hemoglobin', 'Hematocrit']:
                    suggestion = "Counts too low (RBCs) – See \"Approach to the child with anemia\" and \"Diagnostic approach to anemia in adults\"."
                elif param == 'Platelets':
                    suggestion = "Counts too low (Platelets) – See \"Approach to the child with unexplained thrombocytopenia\" and \"Diagnostic approach to thrombocytopenia in adults\"."
                elif param == 'WBC':
                    suggestion = "Counts too low (WBCs) – See \"Evaluation of neutropenia in children and adolescents\" and \"Approach to the adult with unexplained neutropenia\"."
                elif param == 'Neutrophils':
                    suggestion = "Neutropenia – See \"Evaluation of neutropenia in children and adolescents\" or \"Approach to the adult with unexplained neutropenia\"."
                else:
                    suggestion = f"Low {param} – investigate further."
            elif val > rng['max']:
                status = "High"
                if param in ['RBC', 'Hemoglobin', 'Hematocrit']:
                    suggestion = "Counts too high (RBCs) – See \"Diagnostic approach to the patient with erythrocytosis/polycythemia\"."
                elif param == 'Platelets':
                    suggestion = "Counts too high (Platelets) – See \"Approach to the patient with thrombocytosis\"."
                elif param == 'WBC':
                    suggestion = "Counts too high (WBCs) – See \"Approach to the patient with neutrophilia\"."
                elif param == 'Neutrophils':
                    suggestion = "Neutrophilia – See \"Approach to the patient with neutrophilia\"."
                else:
                    suggestion = f"High {param} – investigate further."
            else:
                status = "Normal"
                suggestion = "Within normal range."
            analysis.append({
                'Parameter': rng['desc'],
                'Value': val,
                'Unit': rng['unit'],
                'Status': status,
                'Suggestion': suggestion
            })

    # Rule of Threes (from document)
    if all(k in values for k in ['RBC', 'Hemoglobin', 'Hematocrit']):
        rbc, hb, hct = values['RBC'], values['Hemoglobin'], values['Hematocrit']
        if not (abs(3 * rbc - hb) < 1 and abs(3 * hb - hct) < 3):
            analysis.append({
                'Parameter': 'Rule of Threes',
                'Value': 'Violated',
                'Unit': '',
                'Status': 'Abnormal',
                'Suggestion': "Rule of threes violated – results may be spurious (in otherwise healthy individual) or true hematologic condition present. Recommend blood smear evaluation."
            })

    # RDW / Anemia extra logic (from document)
    if 'RDW' in values and values['RDW'] > NORMAL_RANGES['RDW']['max']:
        rdw_sugg = "High RDW – large variation in RBC sizes; seen in iron deficiency anemia, transfused anemia, myelodysplastic syndromes, hemoglobinopathies. Most useful in microcytic anemia (elevated RDW = iron deficiency vs normal/slightly elevated = thalassemia trait or ACD/AI). Cannot replace iron studies/ferritin."
        analysis.append({'Parameter': 'RDW Interpretation', 'Value': values['RDW'], 'Unit': '%', 'Status': 'Elevated', 'Suggestion': rdw_sugg})

    if 'Hemoglobin' in values and values['Hemoglobin'] < NORMAL_RANGES['Hemoglobin']['min']:
        anemia_sugg = "Decreased Hb typically indicates anemia."
        if 'MCV' in values:
            if values['MCV'] < 80:
                anemia_sugg += " Low MCV – microcytic anemia (See \"Microcytosis/Microcytic anemia\")."
            elif values['MCV'] > 100:
                anemia_sugg += " High MCV – macrocytic anemia (See \"Macrocytosis/Macrocytic anemia\")."
            else:
                anemia_sugg += " Normal MCV – normocytic anemia."
        analysis.append({'Parameter': 'Anemia Evaluation', 'Value': '', 'Unit': '', 'Status': 'Abnormal', 'Suggestion': anemia_sugg + " Consider reticulocyte count and peripheral smear."})

    return analysis

# ────────────────────────────────────────────────
# Streamlit UI
# ────────────────────────────────────────────────

st.title("Blood Analysis Application – CBC Review")
st.markdown("Educational tool based on automated CBC document. Upload PDF/JPG/JPEG or enter manually. Provides step-wise analysis using document logic.")

with st.expander("Collection and Storage Advice (from document)"):
    st.markdown(COLLECTION_ADVICE)

option = st.radio("Input Method", ("Upload File", "Manual Input"))

sample_age_hours = st.number_input("Sample Age (hours since collection)", min_value=0.0, value=0.0, step=1.0)
storage_temp = st.selectbox("Storage Temperature", ["Room Temperature", "Refrigerated", "Frozen", "Heated"])

values = {}

if option == "Upload File":
    uploaded_file = st.file_uploader("Upload PDF, JPG, or JPEG", type=["pdf", "jpg", "jpeg"])
    if uploaded_file:
        if uploaded_file.type == "application/pdf":
            text = extract_text_from_pdf(io.BytesIO(uploaded_file.read()))
        elif uploaded_file.type in ["image/jpeg", "image/jpg", "image/png"]:
            text = extract_text_from_image(io.BytesIO(uploaded_file.read()))
        else:
            text = ""
            st.error("Unsupported file type.")
        if text:
            st.subheader("Step 1: Extracted Text")
            st.text_area("Raw Extracted Text", text, height=250)
            st.subheader("Step 2: Parsed Values")
            values = parse_cbc_values(text)
            if values:
                st.json(values)
            else:
                st.warning("No values parsed – try manual entry or check file quality.")

elif option == "Manual Input":
    st.subheader("Manual CBC Entry")
    cols = st.columns(3)
    i = 0
    for param, info in NORMAL_RANGES.items():
        with cols[i % 3]:
            values[param] = st.number_input(f"{info['desc']} ({info['unit']})", value=0.0, step=0.1, format="%.2f")
        i += 1

if values:
    st.subheader("Step 3: Sample Quality Assessment")
    quality_issues = assess_sample_quality(values, sample_age_hours, storage_temp)
    if quality_issues:
        for issue in quality_issues:
            st.warning(issue)
    else:
        st.success("No major sample quality concerns detected.")

    st.subheader("Step 4: Parameter Analysis")
    analysis_list = analyze_values(values)
    if analysis_list:
        df = pd.DataFrame(analysis_list)
        st.dataframe(df, use_container_width=True)

        st.subheader("Step 5: Summary & Recommendations")
        abnormals = [row for row in analysis_list if row['Status'] != 'Normal']
        if abnormals:
            st.warning(f"{len(abnormals)} abnormality(ies) detected.")
            for row in abnormals:
                st.markdown(f"**{row['Parameter']}**: {row['Value']} {row['Unit']} ({row['Status']})  \n{row['Suggestion']}")
            st.info("Recommend peripheral blood smear review (See \"Evaluation of the peripheral blood smear\"). Consult hematologist if needed. Not a substitute for medical advice.")
        else:
            st.success("All parameters appear within normal ranges.")
    else:
        st.info("No analyzable values.")

st.markdown("---")
st.caption("Educational use only. Always verify with lab-specific ranges and clinical context. Based on provided CBC document excerpts.")
