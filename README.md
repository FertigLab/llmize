# llmize

## Quick json_reduction Tutorial

This project processes JSON data and generates annotated reports with metadata. Follow these steps to run it:

### Prerequisites
- Your JSON data file (Or use already existing multiqc_data.json from data folder)

### Step-by-Step Instructions

1. **Place your JSON file in the data folder**

2. **Navigate to the json_reduction directory**
   ```bash
   cd llmize/json_reduction
   ```

3. **Run the main script**
   ```bash
   python3 main.py
   ```

4. **Follow the prompts**
   - When asked for the JSON filename, enter the name of your file (e.g., `multiqc_data.json`)
   - When asked for the extracted output filename, press Enter to use the default or type a custom name
   - When asked for the annotated report filename, press Enter to use the default or type a custom name
   - The script will create an annotated and broken-down version of your json

### Workflow

The script:
1. **Loads** your JSON file
2. **Extracts** the `report_saved_raw_data` section
3. **Cleans** the data by removing unnecessary fields
4. **Merges** your data with metadata schema annotations
5. **Generates** two output files in the `data/` folder:
   - `extracted_multiqc_data.json` - cleaned extracted data
   - `annotated_report.json` - final report with metadata

### Troubleshooting

**File not found error:**
- Ensure your JSON file is in the `llmize/data/` folder
- Use the exact filename when prompted

**Schema not found:**
- Make sure `descriptor_schema.json` is in the `json_reduction/` folder
- Do not move or rename this file

**JSON parsing error:**
- Verify your input JSON file is valid
- Try opening it in a JSON validator
