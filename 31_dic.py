import re
import json
from typing import List, Dict, Tuple


class December31Extractor:
    """
    Extractor optimizado para identificar todas las variantes de "31 de diciembre"
    en documentos procesados (PDFs legibles convertidos a JSON).
    """
    
    def __init__(self):
        self.patterns = self._build_patterns()
        
    def _build_patterns(self) -> Dict[str, List[re.Pattern]]:
        """Construye patrones regex compilados para cada tipo de formato"""
    
        patterns = {
            "nombre_completo_flexible": [
                # Patrón súper flexible: 31 + hasta 25 caracteres + diciembre
                r"\b31\b.{0,25}?\b(?:diciembre|december)\b",
                r"\b(?:diciembre|december)\b.{0,25}?\b31\b",  # Orden inverso
                
                # Treinta y uno escrito
                r"\b(?:treinta\s+y\s+uno|thirty[\s\-]?first)\b.{0,25}?\b(?:diciembre|december)\b",
                r"\b(?:diciembre|december)\b.{0,25}?\b(?:treinta\s+y\s+uno|thirty[\s\-]?first)\b",
            ],
            
            "nombre_abreviado_flexible": [
                # Con abreviaciones
                r"\b31\b.{0,15}?\b(?:dic\.?|dec\.?)\b",
                r"\b(?:dic\.?|dec\.?)\b.{0,15}?\b31\b",
            ],
            
            "numerico": [
                # Formatos numéricos directos
                r"\b31[/\-.\s]12\b",  # 31/12, 31-12, 31.12, 31 12
                r"\b12[/\-.\s]31\b",  # Formato americano
            ],
            
            "con_año": [
                # Con año incluido (más flexible)
                r"\b31\b.{0,30}?\b(?:diciembre|december|dic\.?|dec\.?)\b.{0,20}?\b(?:19|20)\d{2}\b",
                r"\b(?:diciembre|december|dic\.?|dec\.?)\b.{0,15}?\b31\b.{0,15}?\b(?:19|20)\d{2}\b",
                
                # Formato numérico con año
                r"\b31[/\-.\s]12[/\-.\s](?:\d{2}|\d{4})\b",
                r"\b12[/\-.\s]31[/\-.\s](?:\d{2}|\d{4})\b",
            ],
            
            "patron_estricto": [
                # Mantener algunos patrones estrictos para casos comunes
                r"\b31\s+de\s+diciembre\b",
                r"\b31\s+(?:de\s+)?diciembre\b",
                r"\bdiciembre\s+31\b",
            ]
        }
        
        # Compilar patrones con IGNORECASE para mejor performance
        compiled_patterns = {}
        for category, pattern_list in patterns.items():
            compiled_patterns[category] = [
                re.compile(pattern, re.IGNORECASE | re.DOTALL) for pattern in pattern_list
            ]
        return compiled_patterns
    
    def extract_sentences_with_date(self, text: str) -> List[Dict]:
        """
        Extrae todas las oraciones que contengan referencias al 31 de diciembre.
        
        Args:
            text: Texto completo del documento
            
        Returns:
            Lista de diccionarios con las oraciones y sus matches
        """
        # Dividir en oraciones con manejo inteligente
        sentences = self._split_into_sentences(text)
        results = []
        
        for sentence in sentences:
            matches = self._find_matches_in_sentence(sentence)
            if matches:
                results.append({
                    "sentence": sentence.strip(),
                    "matches": matches
                })
        
        return results
    
    def _split_into_sentences(self, text: str) -> List[str]:
        """
        División inteligente de texto en oraciones, considerando abreviaciones.
        """
        # Proteger abreviaciones comunes para evitar división incorrecta
        abbreviations = ['dic', 'Dic', 'ene', 'feb', 'mar', 'abr', 'may', 'jun', 
                        'jul', 'ago', 'sep', 'oct', 'nov', 'Sr', 'Sra', 'Dr', 'Dra']
        
        protected_text = text
        for abbr in abbreviations:
            protected_text = protected_text.replace(f"{abbr}.", f"{abbr}<<<DOT>>>")
        
        # Patrones para dividir oraciones
        sentence_endings = re.compile(
            r'(?<=[.!?])\s+(?=[A-Z])|'  # Punto seguido de mayúscula
            r'(?<=[.!?])\s*\n+|'  # Punto y salto de línea
            r'\n\n+'  # Doble salto de línea
        )
        
        # Dividir en oraciones
        sentences = sentence_endings.split(protected_text)
        
        # Restaurar puntos en abreviaciones
        sentences = [s.replace("<<<DOT>>>", ".") for s in sentences if s.strip()]
        
        return sentences
    
    def _find_matches_in_sentence(self, sentence: str) -> List[Dict]:
        """
        Busca todas las coincidencias de patrones en una oración.
        Elimina duplicados basados en posición.
        """
        matches = []
        
        for category, pattern_list in self.patterns.items():
            for pattern in pattern_list:
                for match in pattern.finditer(sentence):
                    matches.append({
                        "text": match.group(),
                        "category": category,
                        "position": match.span()
                    })
        
        # Eliminar duplicados basados en posición (misma ubicación en texto)
        unique_matches = []
        seen_positions = set()
        
        for match in matches:
            pos_key = (match["position"][0], match["position"][1])
            if pos_key not in seen_positions:
                seen_positions.add(pos_key)
                unique_matches.append({
                    "text": match["text"],
                    "category": match["category"]
                })
        
        return unique_matches
    
    def process_json_document(self, json_data: Dict) -> Dict:
        """
        Procesa un documento JSON (de PDF convertido) y extrae las referencias.
        
        Args:
            json_data: Diccionario con el contenido del documento
            
        Returns:
            Diccionario con resultados estructurados en JSON
        """
        # Extraer texto del JSON
        text = self._extract_text_from_json(json_data)
        
        # Buscar coincidencias
        results = self.extract_sentences_with_date(text)
        
        return {
            "total_sentences_found": len(results),
            "sentences": results
        }
    
    def _extract_text_from_json(self, json_data: Dict) -> str:
        """
        Extrae texto de la estructura JSON del documento IR (PDF procesado).
        
        Maneja múltiples estructuras posibles:
        - Estructura con páginas: json_data["pages"][]["text"]
        - Estructura con párrafos: json_data["document"]["paragraphs"][]["text"]
        - Estructura plana: json_data["text"]
        """
        try:
            # Estructura con páginas (común en PDFs procesados)
            if "pages" in json_data:
                text_parts = []
                for page in json_data["pages"]:
                    if isinstance(page, dict) and "text" in page:
                        text_parts.append(page["text"])
                    elif isinstance(page, str):
                        text_parts.append(page)
                return "\n".join(text_parts)
            
            # Estructura con document/paragraphs (formato IR estándar)
            elif "document" in json_data and "paragraphs" in json_data["document"]:
                paragraphs = json_data["document"]["paragraphs"]
                text_parts = [p["text"] for p in paragraphs if "text" in p]
                return "\n".join(text_parts)
            
            # Estructura con texto directo
            elif "text" in json_data:
                return json_data["text"]
            
            # Estructura con content
            elif "content" in json_data:
                return json_data["content"]
            
            # Fallback: buscar cualquier campo de texto de forma recursiva
            else:
                text_parts = []
                for key, value in json_data.items():
                    if isinstance(value, str):
                        text_parts.append(value)
                    elif isinstance(value, list):
                        for item in value:
                            if isinstance(item, str):
                                text_parts.append(item)
                            elif isinstance(item, dict) and "text" in item:
                                text_parts.append(item["text"])
                return "\n".join(text_parts)
            
        except Exception as e:
            print(f"Error extracting text: {e}")
        
        return str(json_data)


if __name__ == "__main__":
    import sys
    import glob
    import os
    
    if len(sys.argv) > 1:
        pattern = sys.argv[1]
        files = glob.glob(pattern) if '*' in pattern else [pattern]
        
        output_dir = "/Users/gustavogil/extractor_vigencia_pdf/candidates"
        
        # Crear directorio si no existe
        os.makedirs(output_dir, exist_ok=True)
        
        for filepath in files:
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    json_data = json.load(f)
                
                extractor = December31Extractor()
                results = extractor.process_json_document(json_data)
                
                if results["total_sentences_found"] > 0:
                    # Crear nombre del archivo de salida basado en el original
                    base_name = os.path.basename(filepath).replace('.json', '')
                    output_file = os.path.join(output_dir, f"{base_name}_candidates.json")
                    
                    # Guardar candidatos de este archivo específico
                    with open(output_file, 'w', encoding='utf-8') as f:
                        json.dump({
                            "source_file": filepath,
                            "doc_id": json_data.get("doc_id", "unknown"),
                            "total_sentences": results["total_sentences_found"],
                            "sentences": results["sentences"]
                        }, f, indent=2, ensure_ascii=False)
                    
                    print(f"✓ {base_name}: {results['total_sentences_found']} oraciones → {output_file}")
                    
            except Exception as e:
                print(f"✗ Error en {filepath}: {e}")