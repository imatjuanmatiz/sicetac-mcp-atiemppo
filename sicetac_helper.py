import pandas as pd
from difflib import get_close_matches
import logging
import re
import unicodedata

logging.basicConfig(level=logging.INFO)


def dane_digits(value) -> str:
    """Conserva sólo dígitos de un DANE, sin el cero inicial de columnas numéricas."""
    raw = str(value or "").strip()
    if not raw:
        return ""
    if re.fullmatch(r"\d+\.0+", raw):
        raw = raw.split(".", 1)[0]
    digits = re.sub(r"\D", "", raw)
    if not digits:
        return ""
    return digits.lstrip("0") or "0"


def canonical_municipality_dane(value) -> str:
    """Municipio DIVIPOLA: 68276000 y 68276 identifican el mismo cabecera.

    El catálogo mezcla 5 dígitos (municipio) y 8 dígitos (municipio + 000).
    Un código más largo que no termina en 000 se conserva: es un centro poblado.
    """
    digits = dane_digits(value)
    if not digits:
        return ""
    if digits.endswith("000") and len(digits) >= 7:
        return digits[:-3] or "0"
    return digits


def format_dane_municipality(value) -> str | None:
    """Forma de 8 dígitos para trazabilidad (p. ej. Floridablanca → 68276000)."""
    digits = dane_digits(value)
    if not digits:
        return None
    canon = canonical_municipality_dane(value)
    if len(canon) <= 5:
        return canon.zfill(5) + "000"
    if len(digits) <= 7:
        return digits.zfill(8)
    return digits


def dane_query_pairs(origen, destino) -> list[tuple[str, str]]:
    """Pares OD equivalentes para consultar tablas que guardan 5 u 8 dígitos."""
    seen: set[tuple[str, str]] = set()
    pairs: list[tuple[str, str]] = []

    def add(origin_code, destination_code) -> None:
        origin = str(origin_code or "").strip()
        destination = str(destination_code or "").strip()
        if not origin or not destination or (origin, destination) in seen:
            return
        seen.add((origin, destination))
        pairs.append((origin, destination))

    add(origen, destino)
    add(canonical_municipality_dane(origen), canonical_municipality_dane(destino))
    add(format_dane_municipality(origen), format_dane_municipality(destino))
    add(dane_digits(origen), dane_digits(destino))
    return pairs


class SICETACHelper:
    def __init__(self, municipios_source):
        if isinstance(municipios_source, pd.DataFrame):
            self.df_municipios = municipios_source.copy()
        else:
            self.df_municipios = pd.read_excel(municipios_source)
        self.columnas_municipios = ['nombre_oficial', 'variacion_1', 'variacion_2', 'variacion_3']
        self.codigo_municipio_col = 'codigo_dane'

    def _clean_code(self, value):
        return dane_digits(value) or None

    def _normalize_name(self, value):
        text = str(value or "").strip().upper()
        text = unicodedata.normalize("NFKD", text)
        text = "".join(ch for ch in text if not unicodedata.combining(ch))
        text = re.sub(r"[,;]+", " ", text)
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
        codigo = canonical_municipality_dane(codigo_input)
        if not codigo:
            return None

        if self.codigo_municipio_col not in self.df_municipios.columns:
            logging.warning("✘ Columna codigo_dane no disponible en municipios")
            return None

        serie_codigos = self.df_municipios[self.codigo_municipio_col].map(canonical_municipality_dane)
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
        """Equivalencia → municipio; el catálogo del helper confirma el DANE.

        Un código SICE/DANE publicado no sustituye el municipio ya determinado.
        Si el código no coincide con ese municipio, se conserva el DANE del
        catálogo y se marca el desacuerdo.
        """
        nombre = str(nombre_input or "").strip() or None
        codigo = str(codigo_input or "").strip() or None

        if nombre:
            resultado = self.buscar_municipio(nombre)
            if resultado:
                resultado[self.codigo_municipio_col] = self._clean_code(resultado[self.codigo_municipio_col])
                resultado['resolution_mode'] = 'name'
                resultado['input_nombre'] = nombre
                if codigo:
                    resultado['input_codigo'] = self._clean_code(codigo)
                    if canonical_municipality_dane(codigo) != canonical_municipality_dane(resultado[self.codigo_municipio_col]):
                        resultado['codigo_hint_mismatch'] = True
                return resultado

        if codigo:
            resultado = self.buscar_municipio_por_codigo(codigo)
            if resultado:
                resultado['resolution_mode'] = 'code'
                if nombre:
                    resultado['input_nombre'] = nombre
                return resultado

        return None

    def _split_name_and_department(self, df, nombre_input_norm):
        if "departamento" not in df.columns or not nombre_input_norm:
            return nombre_input_norm, None
        departments = (
            df["departamento"].dropna().map(self._normalize_name).drop_duplicates().tolist()
        )
        for department in sorted(departments, key=len, reverse=True):
            if not department:
                continue
            suffix = " " + department
            if nombre_input_norm.endswith(suffix):
                name = nombre_input_norm[: -len(suffix)].strip()
                if name:
                    return name, department
        return nombre_input_norm, None

    def _row_result(self, row, codigo_col, extra_cols=None, **extra):
        result = {codigo_col: self._clean_code(row[codigo_col])}
        if extra_cols:
            for col in extra_cols:
                if col in row:
                    result[col] = row[col]
        result.update(extra)
        return result

    def _buscar_codigo(self, df, nombre_input, columnas_nombres, codigo_col, extra_cols=None):
        nombre_input = str(nombre_input).strip()
        nombre_input_norm = self._normalize_name(nombre_input)
        search_name, search_dept = self._split_name_and_department(df, nombre_input_norm)
        working = df
        if search_dept and "departamento" in df.columns:
            working = df[df["departamento"].map(self._normalize_name) == search_dept]
            if working.empty:
                working = df

        exact_candidates = []
        for col in columnas_nombres:
            if col in working.columns:
                normalized_col = working[col].map(self._normalize_name)
                match = working[normalized_col == search_name]
                if not match.empty:
                    for _, row in match.iterrows():
                        exact_candidates.append((self._candidate_priority(row, col, search_name), row))

        if exact_candidates:
            exact_candidates.sort(key=lambda item: item[0], reverse=True)
            extra = {"resolution_mode": "name_department"} if search_dept else {}
            return self._row_result(exact_candidates[0][1], codigo_col, extra_cols, **extra)

        if "departamento" in working.columns and "nombre_oficial" in working.columns:
            combinados = (
                working["nombre_oficial"].map(self._normalize_name)
                + " "
                + working["departamento"].map(self._normalize_name)
            )
            match = working[combinados == nombre_input_norm]
            if not match.empty:
                return self._row_result(
                    match.iloc[0], codigo_col, extra_cols, resolution_mode="name_department",
                )

        for col in columnas_nombres:
            if col in working.columns:
                opciones = working[col].dropna().astype(str).map(self._normalize_name).unique().tolist()
                cercanos = get_close_matches(search_name, opciones, n=1, cutoff=0.8)
                if cercanos:
                    normalized_col = working[col].map(self._normalize_name)
                    match = working[normalized_col == cercanos[0]]
                    if not match.empty:
                        ranked = sorted(
                            [(self._candidate_priority(row, col, search_name), row) for _, row in match.iterrows()],
                            key=lambda item: item[0],
                            reverse=True,
                        )
                        return self._row_result(
                            ranked[0][1],
                            codigo_col,
                            extra_cols,
                            coincidencia_aproximada=cercanos[0],
                        )
        return None

    def ruta_existe(self, origen_input, destino_input, df_rutas):
        cod_origen = self.buscar_municipio(origen_input)
        cod_destino = self.buscar_municipio(destino_input)
        if not (cod_origen and cod_destino):
            return False
        origin_key = canonical_municipality_dane(cod_origen['codigo_dane'])
        destination_key = canonical_municipality_dane(cod_destino['codigo_dane'])
        origen_col = df_rutas['codigo_dane_origen'].map(canonical_municipality_dane)
        destino_col = df_rutas['codigo_dane_destino'].map(canonical_municipality_dane)
        existe = df_rutas[(origen_col == origin_key) & (destino_col == destination_key)]
        if existe.empty:
            existe = df_rutas[(origen_col == destination_key) & (destino_col == origin_key)]
        return not existe.empty
