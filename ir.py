#!/usr/bin/env python3
# ir_pdf.py
# Convierte un archivo PDF (sin OCR) a formato intermedio JSON (ir.json) extrayendo texto y tablas

import argparse
import datetime as dt
import hashlib
import json
import re
from pathlib import Path
from typing import Dict, Any, List
import pdfplumber


def sha1_of_file(file_path: Path) -> str:
    """
    Calcula el hash SHA1 de un archivo para identificación única.
    
    Args:
        file_path: Ruta al archivo a procesar
        
    Returns:
        String con el hash SHA1 hexadecimal del archivo
    """
    hash_calculator = hashlib.sha1()
    with open(file_path, "rb") as file_handle:
        # Leer el archivo en chunks de 1MB para eficiencia con archivos grandes
        for chunk in iter(lambda: file_handle.read(1024 * 1024), b""):
            hash_calculator.update(chunk)
    return hash_calculator.hexdigest()


def normalize_space(text_content: str) -> str:
    """
    Normaliza espacios en blanco en el texto, eliminando caracteres especiales
    y espacios múltiples.
    
    Args:
        text_content: Texto a normalizar (puede ser None)
        
    Returns:
        Texto normalizado con espacios simples, string vacío si es None
    """
    if text_content is None:
        return ""
    # Reemplazar espacios no-break, tabs y saltos de línea múltiples
    cleaned_text = text_content.replace("\xa0", " ").replace("\t", " ")
    # Reemplazar saltos de línea múltiples por uno solo
    cleaned_text = re.sub(r'\n+', '\n', cleaned_text)
    # Colapsar múltiples espacios en uno solo
    cleaned_text = re.sub(r' +', ' ', cleaned_text)
    return cleaned_text.strip()


def extract_paragraphs_from_page(page_text: str) -> List[str]:
    """
    Divide el texto de una página en párrafos basándose en saltos de línea.
    
    Args:
        page_text: Texto completo de una página
        
    Returns:
        Lista de párrafos normalizados no vacíos
    """
    if not page_text:
        return []
    
    # Dividir por doble salto de línea o más (párrafos típicos)
    # Si no hay dobles saltos, dividir por saltos simples
    if '\n\n' in page_text:
        raw_paragraphs = page_text.split('\n\n')
    else:
        raw_paragraphs = page_text.split('\n')
    
    # Normalizar y filtrar párrafos vacíos
    paragraphs = []
    for paragraph in raw_paragraphs:
        normalized = normalize_space(paragraph)
        if normalized and len(normalized) > 1:  # Ignorar párrafos de un solo carácter
            paragraphs.append(normalized)
    
    return paragraphs


def extract_paragraphs(pdf_path: Path) -> List[Dict[str, Any]]:
    """
    Extrae todos los párrafos con contenido del documento PDF.
    
    Args:
        pdf_path: Ruta al archivo PDF
        
    Returns:
        Lista de diccionarios con índice y texto de cada párrafo no vacío
    """
    extracted_paragraphs = []
    paragraph_index = 0
    
    with pdfplumber.open(pdf_path) as pdf:
        for page_num, page in enumerate(pdf.pages, 1):
            # Extraer texto de la página
            page_text = page.extract_text()
            
            if page_text:
                # Dividir en párrafos
                page_paragraphs = extract_paragraphs_from_page(page_text)
                
                for paragraph_text in page_paragraphs:
                    extracted_paragraphs.append({
                        "index": paragraph_index,
                        "text": paragraph_text,
                        "page": page_num  # Información adicional útil para PDFs
                    })
                    paragraph_index += 1
    
    return extracted_paragraphs


def clean_table_data(table_data: List[List[Any]]) -> List[List[str]]:
    """
    Limpia y normaliza los datos de una tabla extraída.
    
    Args:
        table_data: Datos crudos de la tabla extraída por pdfplumber
        
    Returns:
        Tabla con celdas normalizadas como strings
    """
    cleaned_table = []
    for row in table_data:
        cleaned_row = []
        for cell in row:
            if cell is None:
                cleaned_row.append("")
            else:
                # Convertir a string y normalizar
                cell_text = str(cell).strip()
                # Reemplazar saltos de línea internos por espacios
                cell_text = cell_text.replace('\n', ' ')
                cleaned_row.append(normalize_space(cell_text))
        cleaned_table.append(cleaned_row)
    
    return cleaned_table


def extract_tables(pdf_path: Path) -> List[Dict[str, Any]]:
    """
    Extrae todas las tablas del documento PDF.
    
    Args:
        pdf_path: Ruta al archivo PDF
        
    Returns:
        Lista de diccionarios con información de cada tabla (id, dimensiones, datos)
    """
    extracted_tables = []
    table_index = 0
    
    with pdfplumber.open(pdf_path) as pdf:
        for page_num, page in enumerate(pdf.pages, 1):
            # Extraer tablas de la página
            page_tables = page.extract_tables()
            
            for table_data in page_tables:
                if not table_data or not any(table_data):  # Saltar tablas vacías
                    continue
                
                # Limpiar datos de la tabla
                cleaned_data = clean_table_data(table_data)
                
                # Determinar dimensiones reales (algunas filas pueden tener menos columnas)
                max_cols = max(len(row) for row in cleaned_data) if cleaned_data else 0
                
                # Normalizar longitud de filas
                normalized_rows = []
                for row in cleaned_data:
                    normalized_row = row + [''] * (max_cols - len(row))
                    normalized_rows.append(normalized_row)
                
                # Filtrar tablas que sean demasiado pequeñas o vacías
                if len(normalized_rows) > 0 and max_cols > 0:
                    # Verificar que la tabla tenga al menos algún contenido
                    has_content = any(
                        any(cell.strip() for cell in row)
                        for row in normalized_rows
                    )
                    
                    if has_content:
                        extracted_tables.append({
                            "table_id": f"t{table_index}",
                            "rows": len(normalized_rows),
                            "cols": max_cols,
                            "data": normalized_rows,
                            "page": page_num  # Información adicional útil para PDFs
                        })
                        table_index += 1
    
    return extracted_tables


def build_ir(input_document_path: Path) -> Dict[str, Any]:
    """
    Construye la representación intermedia (IR) completa del documento PDF.
    
    Args:
        input_document_path: Ruta al archivo PDF de entrada
        
    Returns:
        Diccionario con toda la estructura IR incluyendo metadatos,
        contenido extraído y estadísticas
    """
    # Verificar que el archivo sea un PDF
    if input_document_path.suffix.lower() != '.pdf':
        raise ValueError(f"El archivo {input_document_path} no es un PDF")
    
    # Extraer componentes principales
    document_paragraphs = extract_paragraphs(input_document_path)
    document_tables = extract_tables(input_document_path)
    
    # Calcular hash para identificación única
    document_hash = sha1_of_file(input_document_path)
    
    # Obtener información adicional del PDF
    pdf_metadata = {}
    try:
        with pdfplumber.open(input_document_path) as pdf:
            pdf_metadata = {
                "page_count": len(pdf.pages),
                "metadata": pdf.metadata if pdf.metadata else {}
            }
    except Exception as e:
        print(f"Advertencia: No se pudo extraer metadata del PDF: {e}")
        pdf_metadata = {"page_count": 0, "metadata": {}}
    
    # Construir estructura IR completa (compatible con la estructura original)
    intermediate_representation = {
        "ir_version": "1.0",
        "created_at": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
        "source": {
            "path": str(input_document_path.resolve()),
            "filename": input_document_path.name,
            "sha1": document_hash,
            "mimetype": "application/pdf",
        },
        "doc_id": document_hash[:12],  # Usar primeros 12 caracteres del hash como ID
        "document": {
            "paragraphs": document_paragraphs,
            "tables": document_tables,
        },
        "stats": {
            "paragraph_count": len(document_paragraphs),
            "table_count": len(document_tables),
            "page_count": pdf_metadata.get("page_count", 0),
        },
        "pdf_metadata": pdf_metadata.get("metadata", {})
    }
    
    return intermediate_representation


def validate_pdf_readable(pdf_path: Path) -> bool:
    """
    Valida que el PDF contenga texto extraíble (no requiere OCR).
    
    Args:
        pdf_path: Ruta al archivo PDF
        
    Returns:
        True si el PDF tiene texto extraíble, False si probablemente necesita OCR
    """
    try:
        with pdfplumber.open(pdf_path) as pdf:
            # Revisar las primeras páginas para ver si tienen texto
            pages_to_check = min(5, len(pdf.pages))
            text_found = False
            
            for i in range(pages_to_check):
                page_text = pdf.pages[i].extract_text()
                if page_text and len(page_text.strip()) > 10:
                    text_found = True
                    break
            
            if not text_found:
                print("⚠️  Advertencia: El PDF parece no contener texto extraíble.")
                print("    Es posible que sea un PDF escaneado que requiera OCR.")
                return False
            
            return True
            
    except Exception as e:
        print(f"Error al validar el PDF: {e}")
        return False


def main():
    """
    Función principal que procesa argumentos de línea de comandos
    y ejecuta la conversión de PDF a IR JSON.
    """
    # Configurar parser de argumentos
    argument_parser = argparse.ArgumentParser(
        description="Convierte archivos PDF (sin OCR) a formato intermedio JSON (ir.json)"
    )
    argument_parser.add_argument(
        "input_pdf", 
        type=str, 
        help="Ruta al archivo PDF de entrada"
    )
    argument_parser.add_argument(
        "-o", "--output", 
        type=str, 
        default=None, 
        help="Ruta del JSON de salida (por defecto: /Users/gustavogil/extractor_vigencia_pdf/ir_output/)"
    )
    argument_parser.add_argument(
        "--force", 
        action="store_true",
        help="Forzar procesamiento incluso si el PDF parece requerir OCR"
    )
    
    parsed_args = argument_parser.parse_args()
    
    # Validar archivo de entrada
    input_file_path = Path(parsed_args.input_pdf)
    if not input_file_path.exists():
        raise FileNotFoundError(f"No existe el archivo: {input_file_path}")
    
    # Validar que sea un PDF
    if input_file_path.suffix.lower() != '.pdf':
        raise ValueError(f"El archivo debe ser un PDF, recibido: {input_file_path.suffix}")
    
    # Validar que el PDF tenga texto extraíble
    if not parsed_args.force:
        if not validate_pdf_readable(input_file_path):
            print("\n❌ El PDF parece requerir OCR. Use --force para procesar de todos modos.")
            return
    
    print(f"📄 Procesando PDF: {input_file_path.name}")
    
    # Construir representación intermedia
    try:
        ir_document = build_ir(input_file_path)
    except Exception as e:
        print(f"❌ Error al procesar el PDF: {e}")
        return
    
    # Determinar archivo de salida
    if parsed_args.output:
        # Si se especifica una salida personalizada, usarla
        output_file_path = Path(parsed_args.output)
    else:
        # Directorio de salida por defecto
        output_dir = Path("/Users/gustavogil/extractor_vigencia_pdf/ir_output")
        # Crear el directorio si no existe
        output_dir.mkdir(parents=True, exist_ok=True)
        # Generar nombre único basado en el nombre del PDF original
        output_filename = f"{input_file_path.stem}_ir.json"
        output_file_path = output_dir / output_filename
    
    # Guardar resultado en JSON
    with open(output_file_path, "w", encoding="utf-8") as output_file:
        json.dump(ir_document, output_file, ensure_ascii=False, indent=2)
    
    print(f"✔ Conversión completada: {input_file_path.name} → {output_file_path}")
    print(f"  - Párrafos extraídos: {ir_document['stats']['paragraph_count']}")
    print(f"  - Tablas extraídas: {ir_document['stats']['table_count']}")
    print(f"  - Páginas procesadas: {ir_document['stats'].get('page_count', 'N/A')}")


if __name__ == "__main__":
    main()