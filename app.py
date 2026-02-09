# app.py - Expanded Streamlit app for Blood Analysis based on CBC Document Knowledge

import streamlit as st
import PyPDF2
from PIL import Image
import pytesseract
import re
import io
import pandas as pd

# Expanded hardcoded normal ranges (sourced from general medical knowledge and document; can be updated)
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

# Collection and Storage Advice from Document
COLLECTION_ADVICE = """
**Collection Advice:**
- Perform phlebotomy by a trained phlebotomist.
- Use EDTA (purple top) or sodium citrate (blue top) tubes.
- Avoid underfilling or overfilling tubes to prevent inaccurate results.
- Avoid hemolysis: Use appropriate needle gauge, avoid tight tourniquets.
- Do not collect proximal to an IV line to prevent dilution.

**Storage Advice:**
- Keep at room temperature for analysis within 24 hours.
- Refrigerate for analysis up to 72 hours.
- Avoid freezing or heat exposure.
- Samples >72 hours old may show spurious results (e.g., elevated MCV, MPV).
- Prepare blood films within 8 hours.
"""

# Function to extract text from PDF
def extract_text_from_pdf(file):
    pdf_reader = PyPDF2.PdfReader(file)
    text = ""
    for page in pdf_reader.pages:
        text += page.extract_text() + "\n"
    return text

# Function to extract text from image using OCR
def extract_text_from_image(file):
    image = Image.open(file)
    text = pytesseract.image_to_string(image)
    return text

# Expanded function to parse CBC values from text using regex
def parse_cbc_values(text):
    patterns = {
        'RBC': r'RBC[\s:]*([\d\.]+)',
        'Hemoglobin': r'Hemoglobin|Hb[\s:]*([\d\.]+)',
        'Hematocrit': r'Hematocrit|HCT[\s:]*([\d\.]+)',
        'MCV': r'MCV[\s:]*([\d\.]+)',
        'MCH': r'MCH[\s:]*([\d\.]+)',
        'MCHC': r'MCHC[\s:]*([\d\.]+)',
        'RDW': r'RDW[\s:]*([\d\.]+)',
        'WBC': r'WBC[\s:]*([\d\.]+)',
        'Neutrophils': r'Neutrophils|NEU[\s:]*([\d\.]+)',
        'Lymphocytes': r'Lymphocytes|LYM[\s:]*([\d\.]+)',
        'Monocytes': r'Monocytes|MON[\s:]*([\d\.]+)',
        'Eosinophils': r'Eosinophils|EOS[\s:]*([\d\.]+)',
        'Basophils': r'Basophils|BAS[\s:]*([\d\.]+)',
        'Platelets': r'Platelets|PLT[\s:]*([\d\.]+)',
        'MPV': r'MPV[\s:]*([\d\.]+)',
        'Reticulocytes': r'Reticulocytes|RET[\s:]*([\d\.]+)',
    }
    values = {}
    for key, pattern in patterns.items():
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            try:
                values[key] = float(match.group(1))
            except ValueError:
                pass
    return values

# Function to assess sample quality based on values and user input
def assess_sample_quality(values, sample_age_hours, storage_temp):
    quality_issues = []
    if sample_age_hours > 72:
        quality_issues.append("Sample >72 hours old: May show spurious elevated MCV and MPV due to cell swelling.")
    if storage_temp == "Frozen":
        quality_issues.append("Freezing causes cell lysis, leading to inaccurate counts.")
    if storage_temp == "Heated":
        quality_issues.append("Heat exposure causes RBC fragmentation, mimicking burn victim samples.")
    if 'MCV' in values and values['MCV'] > 100:
        quality_issues.append("Elevated MCV may indicate old sample or macrocytosis.")
    if 'MPV' in values and 'MPV' in NORMAL_RANGES and values['MPV'] > NORMAL_RANGES['MPV']['max']:
        quality_issues.append("Elevated MPV suggests prolonged EDTA exposure.")
    if 'Hemoglobin' in values and 'RBC' in values and values['Hemoglobin'] < NORMAL_RANGES['Hemoglobin']['min'] and values['RBC'] < NORMAL_RANGES['RBC']['min']:
        quality_issues.append("Possible hemolysis: Low Hb and RBC due to shearing during collection.")
    return quality_issues

# Expanded function to analyze values based on document and searched knowledge
def analyze_values(values):
    analysis = []
    for param, val in values.items():
        if param in NORMAL_RANGES:
            range_info = NORMAL_RANGES[param]
            if val < range_info['min']:
                status = "Low"
                if param == 'RBC':
                    suggestion = "Possible anemia. Evaluate with MCV classification (microcytic, normocytic, macrocytic). Refer to 'Diagnostic approach to anemia in adults' or 'Approach to the child with anemia'. Consider reticulocyte count for production vs. loss/destruction."
                elif param == 'Platelets':
                    suggestion = "Thrombocytopenia. Refer to 'Approach to the child with unexplained thrombocytopenia' or 'Diagnostic approach to thrombocytopenia in adults'."
                elif param == 'WBC':
                    suggestion = "Neutropenia or lymphopenia possible. Refer to 'Evaluation of neutropenia in children and adolescents' or 'Approach to the adult with unexplained neutropenia'. If low lymphocytes, consider primary immunodeficiency disorders (PID): Check absolute lymphocyte count (ALC); low ALC suggests T-cell disorder."
                elif param == 'Neutrophils':
                    suggestion = "Neutropenia: Increased infection risk. Evaluate for phagocytic disorders or PID. Series of CBCs needed for confirmation."
                elif param == 'Lymphocytes':
                    suggestion = "Lymphopenia: Possible T-cell deficiency. In PID, low ALC on CBC prompts further immunoglobulin and complement testing."
                else:
                    suggestion = f"Low {param}. Investigate further."
            elif val > range_info['max']:
                status = "High"
                if param == 'RBC':
                    suggestion = "Erythrocytosis/polycythemia. Refer to 'Diagnostic approach to the patient with erythrocytosis/polycythemia'."
                elif param == 'Platelets':
                    suggestion = "Thrombocytosis. Refer to 'Approach to the patient with thrombocytosis'."
                elif param == 'WBC':
                    suggestion = "Neutrophilia or leukocytosis. Refer to 'Approach to the patient with neutrophilia'. Check for infection, inflammation, or malignancy. Review peripheral smear for left shift."
                elif param == 'Neutrophils':
                    suggestion = "Neutrophilia (>7.7 x10^9/L). Evaluate CBC with differential and smear. Causes: Infection, stress, malignancy. If persistent, consider bone marrow biopsy."
                else:
                    suggestion = f"High {param}. Investigate further."
            else:
                status = "Normal"
                suggestion = "Within normal range."
            analysis.append({
                'Parameter': range_info['desc'],
                'Value': val,
                'Unit': range_info['unit'],
                'Status': status,
                'Suggestion': suggestion
            })
    # Rule of Threes
    if 'RBC' in values and 'Hemoglobin' in values and 'Hematocrit' in values:
        rbc = values['RBC']
        hb = values['Hemoglobin']
        hct = values['Hematocrit']
        if not (abs(3 * rbc - hb) < 1 and abs(3 * hb - hct) < 3):
            analysis.append({
                'Parameter': 'Rule of Threes',
                'Value': 'Violated',
                'Unit': '',
                'Status': 'Abnormal',
                'Suggestion': "Results may be spurious or indicate a true hematologic condition. Recommend blood smear evaluation."
            })
    # Additional for Anemia if low Hb/RBC
    if 'Hemoglobin' in values and values['Hemoglobin'] < NORMAL_RANGES['Hemoglobin']['min']:
        anemia_type = ""
        if 'MCV' in values:
            if values['MCV'] < 80:
                anemia_type = "Microcytic: Possible iron deficiency or thalassemia."
            elif values['MCV'] > 100:
                anemia_type = "Macrocytic: Possible B12/folate deficiency."
            else:
                anemia_type = "Normocytic: Possible chronic disease or hemolysis."
        analysis.append({
            'Parameter': 'Anemia Evaluation',
            'Value': '',
            'Unit': '',
            'Status': 'Abnormal',
            'Suggestion': f"Low Hb indicates anemia. {anemia_type} Use reticulocyte count to assess production. Peripheral smear for morphology."
        })
    # For PID if low WBC/Lymphocytes
    if 'Lymphocytes' in values and values['Lymphocytes'] < NORMAL_RANGES['Lymphocytes']['min']:
        analysis.append({
            'Parameter': 'Possible PID',
            'Value': '',
            'Unit': '',
            'Status': 'Abnormal',
            'Suggestion': "Low lymphocytes: Consider primary immunodeficiency. Initial tests: CBC with ALC, immunoglobulins, complement. If low ALC, evaluate T-cell function."
        })
    return analysis

# Streamlit App
st.title("Expanded Blood Analysis Application")
st.markdown("Based on CBC document. Upload report (PDF/JPG/JPEG) or enter manually. Includes sample quality, collection/storage advice, anemia/neutrophilia evaluation, PID considerations.")

# Display Collection and Storage Advice
with st.expander("Collection and Storage Advice"):
    st.markdown(COLLECTION_ADVICE)

# Option selection
option = st.radio("Input Method", ("Upload File", "Manual Input"))

values = {}
sample_age_hours = st.number_input("Sample Age (hours since collection)", min_value=0.0, value=0.0)
storage_temp = st.selectbox("Storage Temperature", ["Room Temperature", "Refrigerated", "Frozen", "Heated"])

if option == "Upload File":
    uploaded_file = st.file_uploader("Upload PDF, JPG, or JPEG", type=["pdf", "jpg", "jpeg"])
    if uploaded_file:
        file_type = uploaded_file.type
        if file_type == "application/pdf":
            text = extract_text_from_pdf(io.BytesIO(uploaded_file.read()))
        elif file_type in ["image/jpeg", "image/jpg"]:
            text = extract_text_from_image(io.BytesIO(uploaded_file.read()))
        else:
            st.error("Unsupported file type.")
            text = ""
        if text:
            st.subheader("Step 1: Extracted Text from File")
            st.text_area("Raw Text", text, height=200)
            
            st.subheader("Step 2: Parsed CBC Values")
            values = parse_cbc_values(text)
            if values:
                st.json(values)
            else:
                st.warning("No CBC values found. Try manual input.")

elif option == "Manual Input":
    st.subheader("Enter CBC Values Manually")
    for param in NORMAL_RANGES:
        values[param] = st.number_input(f"{NORMAL_RANGES[param]['desc']} ({NORMAL_RANGES[param]['unit']})", min_value=0.0, step=0.1)

# Analysis if values are provided
if values:
    st.subheader("Step 3: Sample Quality Assessment")
    quality_issues = assess_sample_quality(values, sample_age_hours, storage_temp)
    if quality_issues:
        st.warning("Potential Sample Quality Issues:")
        for issue in quality_issues:
            st.markdown(f"- {issue}")
    else:
        st.success("No apparent sample quality issues.")

    st.subheader("Step 4: Analysis and Reporting")
    analysis = analyze_values(values)
    if analysis:
        df = pd.DataFrame(analysis)
        st.table(df)
        
        st.subheader("Step 5: Summary Report")
        abnormal = [a for a in analysis if a['Status'] != 'Normal']
        if abnormal:
            st.warning("Abnormalities detected. Recommendations:")
            for a in abnormal:
                st.markdown(f"- **{a['Parameter']}**: {a['Value']} {a['Unit']} ({a['Status']}) - {a['Suggestion']}")
            st.info("Consider peripheral blood smear, further tests, or consult specialist. For PID: If low lymphocytes, test immunoglobulins/complement.")
        else:
            st.success("All values within normal ranges.")
    else:
        st.info("No values to analyze.")

# Footer
st.markdown("---")
st.markdown("For educational purposes only. Not medical advice.")
st.markdown("GitHub Deployment: Add app.py, requirements.txt (streamlit, PyPDF2, pillow, pytesseract, pandas, regex). Ensure Tesseract installed.")
