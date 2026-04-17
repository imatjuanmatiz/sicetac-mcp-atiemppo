import pandas as pd
from difflib import get_close_matches
import logging
import re
import unicodedata

logging.basicConfig(level=logging.INFO)

class SICETACHelper:
    def __init__(self, municipios_source):
        if isinstance(municipios_source, pd.DataFrame):
            self.df_municipios = municipios_source.copy()
        else:
            self.df_municipios = pd.read_excel(municipios_source)
        self.columnas_municipios = ['nombre_oficial', 'variacion_1', 'variacion_2', 'variacion_3']
        self.codigo_municipio_col = 'codigo_dane'

    def _clean_code(self, value):
        raw = str(value or "").strip()
        if not raw:
            return None
        digits = re.sub(r"\D", "", raw)
        if digits:
            return digits
        if raw.endswith(".0"):
            raw = raw[:-2]
        return raw or None

    def _normalize_name(self, value):
        text = str(value or "").strip().upper()
        text = unicodedata.normalize("NFKD", text)
        text = "".join(ch for ch in text if not unicodedata.combining(ch))
        text = re.sub(r"\s+", " ", text)
        return text

    def _candidate_priority(self, row, matched_col, original_input):
        nombre_oficial = self._normalize_name(row.get("nombre_oficial"))
        original_norm = self._normalize_name(original_input)
        score = 0
        if matched_col == "nombre_oficial":
            score += 100
        if nombre_oficial == original_norm:
            score += 50
        if " " not in nombre_oficial:
            score += 10
        score -= len(nombre_oficial) / 100.0
        return score

    def buscar_municipio(self, nombre_input):
        resultado = self._buscar_codigo(
            self.df_municipios,
            nombre_input,
            self.columnas_municipios,
            self.codigo_municipio_col,
            ['departamento', 'nombre_oficial']
        )
        if resultado:
            logging.info(f"✔ Municipio encontrado: {resultado}")
        else:
            logging.warning(f"✘ Municipio NO encontrado: {nombre_input}")
        return resultado

    def buscar_municipio_por_codigo(self, codigo_input):
        codigo = self._clean_code(codigo_input)
        if not codigo:
            return None

        if self.codigo_municipio_col not in self.df_municipios.columns:
            logging.warning("✘ Columna codigo_dane no disponible en municipios")
            return None

        serie_codigos = self.df_municipios[self.codigo_municipio_col].map(self._clean_code)
        match = self.df_municipios[serie_codigos == codigo]
        if match.empty:
            logging.warning(f"✘ Municipio NO encontrado por código: {codigo_input}")
            return None

        row = match.iloc[0]
        result = {self.codigo_municipio_col: self._clean_code(row[self.codigo_municipio_col])}
        for c in ['departamento', 'nombre_oficial']:
            if c in row:
                result[c] = row[c]
        result['matched_by_code'] = True
        logging.info(f"✔ Municipio encontrado por código: {result}")
        return result

    def resolver_municipio_input(self, nombre_input=None, codigo_input=None):
        if codigo_input is not None and str(codigo_input).strip():
            resultado = self.buscar_municipio_por_codigo(codigo_input)
            if resultado:
                resultado['resolution_mode'] = 'code'
                if nombre_input is not None and str(nombre_input).strip():
                    resultado['input_nombre'] = str(nombre_input).strip()
                return resultado

        if nombre_input is not None and str(nombre_input).strip():
            resultado = self.buscar_municipio(nombre_input)
            if resultado:
                resultado[self.codigo_municipio_col] = self._clean_code(resultado[self.codigo_municipio_col])
                resultado['resolution_mode'] = 'name'
                resultado['input_nombre'] = str(nombre_input).strip()
                if codigo_input is not None and str(codigo_input).strip():
                    resultado['input_codigo'] = self._clean_code(codigo_input)
                return resultado

        return None

    def _buscar_codigo(self, df, nombre_input, columnas_nombres, codigo_col, extra_cols=None):
        nombre_input = str(nombre_input).strip()
        nombre_input_norm = self._normalize_name(nombre_input)
        exact_candidates = []
        for col in columnas_nombres:
            if col in df.columns:
                normalized_col = df[col].map(self._normalize_name)
                match = df[normalized_col == nombre_input_norm]
                if not match.empty:
                    for _, row in match.iterrows():
                        exact_candidates.append((self._candidate_priority(row, col, nombre_input), row))

        if exact_candidates:
            exact_candidates.sort(key=lambda item: item[0], reverse=True)
            row = exact_candidates[0][1]
            result = {codigo_col: self._clean_code(row[codigo_col])}
            if extra_cols:
                for c in extra_cols:
                    if c in row:
                        result[c] = row[c]
            return result

        for col in columnas_nombres:
            if col in df.columns:
                opciones = df[col].dropna().astype(str).map(self._normalize_name).unique().tolist()
                cercanos = get_close_matches(nombre_input_norm, opciones, n=1, cutoff=0.8)
                if cercanos:
                    normalized_col = df[col].map(self._normalize_name)
                    match = df[normalized_col == cercanos[0]]
                    if not match.empty:
                        ranked = sorted(
                            [(self._candidate_priority(row, col, nombre_input), row) for _, row in match.iterrows()],
                            key=lambda item: item[0],
                            reverse=True,
                        )
                        row = ranked[0][1]
                        result = {codigo_col: self._clean_code(row[codigo_col])}
                        if extra_cols:
                            for c in extra_cols:
                                if c in row:
                                    result[c] = row[c]
                        result['coincidencia_aproximada'] = cercanos[0]
                        return result
        return None

    def ruta_existe(self, origen_input, destino_input, df_rutas):
        cod_origen = self.buscar_municipio(origen_input)
        cod_destino = self.buscar_municipio(destino_input)
        if cod_origen and cod_destino:
            existe = df_rutas[
                (df_rutas['codigo_dane_origen'] == cod_origen['codigo_dane']) &
                (df_rutas['codigo_dane_destino'] == cod_destino['codigo_dane'])
            ]
            return not existe.empty
        return False
