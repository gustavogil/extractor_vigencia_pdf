import json
from openai import OpenAI
from typing import List, Dict, Any
import os

# Configuración de OpenAI
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

def create_extraction_prompt() -> str:
    """
    Crea un prompt siguiendo los lineamientos de GPT-5:
    - Estructuras XML claras
    - Instrucciones precisas sin contradicciones
    - Criterios explícitos de inclusión/exclusión
    """
    
    prompt = """
<contract_validity_extraction>
You are an expert in extracting contract validity periods from Mexican public procurement documents.

<extraction_objective>
Extract ALL sentences that contain contract validity periods (vigencia del contrato). There may be multiple validity periods for different products or services.
</extraction_objective>

<inclusion_criteria>
PRIORITIZE semantic meaning over exact words. If the context clearly indicates:
- Main contract duration OR
- Primary delivery period for goods and services that defines the contract scope
- "Suministro" (supply) periods that are not the main contract period
- With a date range (start and end dates)
Then SELECT it, even without the exact word "vigencia"
Reason first about the semantic context, then decide.
SELECT ALL sentences that match - there can be multiple validity periods.
</inclusion_criteria>

<double_review_criteria>
BEFORE CHOOSING sentences about the following terms, review IF the sentence IS really about contract validity:
- "Vigencia de cotización" (quotation validity)
- Payment terms or credit periods
- Warranty periods that are not the main contract duration
- IMSS
- SAT
- IVA
</double_review_criteria>

<golden_examples>
1. "La vigencia del contrato será del 1° de enero de 2025 al 31 de diciembre de 2025."
2. "El (los) contrato(s) que, en su caso, sea(n) formalizado(s) con motivo de este procedimiento de contratación será(n) de carácter anual, y contará(n) con un período de vigencia a partir del fallo al 31 de diciembre de 2025."
3. "La vigencia de la contratación será a partir del día natural siguiente a la fecha de emisión del fallo y hasta el 31 de diciembre de 2025."
4. "El contrato permanecerá vigente desde el día de la notificación de fallo y hasta el 31 de diciembre del 2025."
</golden_examples>

<preprocessing_instructions>
When analyzing sentences:
- Ignore structural text (ÍNDICE, GLOSARIO, headers unrelated to contract)
- Focus on contractual information regardless of formatting
- Clean multiple line breaks mentally when understanding the context
</preprocessing_instructions>

<task_instructions>
1. Analyze each sentence in the input
2. Identify which sentences contain contract validity information
3. Reason internally about why each sentence should be selected or rejected
4. Return ONLY the selected sentences
</task_instructions>

<output_format>
Return a JSON object with this structure:
{
    "selected_sentences": ["first selected sentence verbatim", "second selected sentence verbatim", ...]
}

If no sentences contain validity information, return:
{
    "selected_sentences": []
}

IMPORTANT: Return ONLY the JSON object, no additional text or reasoning.
</output_format>
</contract_validity_extraction>

Analyze the following sentences and extract the main contract validity period:

<sentences>
{sentences}
</sentences>

Remember: Focus on ALL contract validity periods. Return only the JSON with selected sentences."""
    
    return prompt

def process_document(json_file_path: str) -> Dict[str, Any]:
    """
    Procesa un documento JSON y extrae la vigencia del contrato
    """
    # Cargar el archivo JSON
    with open(json_file_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    # Extraer todas las oraciones únicas
    unique_sentences = set()
    for item in data.get('sentences', []):
        unique_sentences.add(item['sentence'])
    
    # Formatear las oraciones para el prompt
    sentences_text = "\n".join([f"{i+1}. {sent}" for i, sent in enumerate(unique_sentences)])
    
    # Crear el prompt
    prompt = create_extraction_prompt()
    final_prompt = prompt.replace("{sentences}", sentences_text)
    
    # Llamar a GPT-5 mini
    try:
        response = client.chat.completions.create(
            model="gpt-5-mini",  # Usar GPT-5 mini
            messages=[
                {
                    "role": "system",
                    "content": "You are a precise document analyzer. Follow the instructions exactly and provide only JSON output."
                },
                {
                    "role": "user",
                    "content": final_prompt
                }
            ],
            max_completion_tokens=2000
        )
        
        # Parsear la respuesta JSON
        result_text = response.choices[0].message.content
        
        # Intentar extraer JSON de la respuesta
        import re
        json_match = re.search(r'\{.*\}', result_text, re.DOTALL)
        if json_match:
            result = json.loads(json_match.group())
        else:
            result = {"selected_sentences": []}
            
    except Exception as e:
        result = {"selected_sentences": [], "error": str(e)}
    
    return result

def main():
    """
    Procesa todos los archivos JSON en el directorio output
    """
    import glob
    
    # Obtener todos los archivos JSON - RUTA ACTUALIZADA
    json_files = glob.glob("/Users/gustavogil/extractor_vigencia_docx/candidatos/*.json")
    
    # Crear directorio para outputs si no existe - RUTA ACTUALIZADA
    output_dir = "/Users/gustavogil/extractor_vigencia_pdf/vigencias_extraidas"
    os.makedirs(output_dir, exist_ok=True)
    
    summary = []
    
    for json_file in json_files:
        print(f"\nProcesando: {json_file}")
        result = process_document(json_file)
        
        # Guardar resultado individual
        base_name = os.path.basename(json_file).replace('.json', '_vigencia.json')
        output_path = os.path.join(output_dir, base_name)
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        
        # Agregar al resumen
        num_sentences = len(result.get("selected_sentences", []))
        summary.append({
            "archivo": os.path.basename(json_file),
            "vigencias_encontradas": num_sentences
        })
        
        # Mostrar resultado
        print(f"Resultado para {os.path.basename(json_file)}:")
        if num_sentences > 0:
            print(f"  ✓ {num_sentences} vigencia(s) encontrada(s)")
            for sent in result["selected_sentences"][:1]:  # Mostrar solo la primera como preview
                print(f"    Preview: {sent[:100]}...")
        else:
            print("  ✗ No se encontró vigencia del contrato")
        
        print(f"  Guardado en: {output_path}")
    
    # Resumen
    successful = sum(1 for s in summary if s["vigencias_encontradas"] > 0)
    print(f"\n📊 Resumen: {successful}/{len(summary)} documentos con vigencia extraída")
    print(f"✅ Archivos JSON individuales guardados en: {output_dir}/")

if __name__ == "__main__":
    main()