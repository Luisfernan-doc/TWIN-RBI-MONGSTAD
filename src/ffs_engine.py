# ============================================================
# ffs_engine.py  —  API 579-1/ASME FFS-1  Level 1
# Motor de evaluación Fitness-for-Service
# TWIN-RBI Mongstad  —  AIM Consulting
# Soporta: pipes, vessels, exchangers
# ============================================================

import numpy as np
import pandas as pd
from dataclasses import dataclass, field
from typing import Optional
import warnings
warnings.filterwarnings('ignore')

# ── Propiedades de materiales (ASME Sec II Part D) ───────────
MATERIAL_PROPS = {
    'CS A106-B'  : {'S_mpa': 103.4, 'UTS': 414, 'YS': 241, 'E': 200000},
    'CS A333-6'  : {'S_mpa': 103.4, 'UTS': 414, 'YS': 241, 'E': 200000},
    'CS A516-70' : {'S_mpa': 137.9, 'UTS': 483, 'YS': 260, 'E': 200000},
    'CS A53-B'   : {'S_mpa':  93.1, 'UTS': 414, 'YS': 241, 'E': 200000},
}

# ── Dataclass resultado FFS ───────────────────────────────────
@dataclass
class FFSResult:
    tag             : str
    asset_type      : str

    # Espesores
    t_nominal_mm    : float
    t_actual_mm     : float
    t_min_mm        : float
    t_required_mm   : float
    t_margin_mm     : float
    remaining_life_yr: float

    # MAWP
    MAWP_bar        : float
    P_oper_bar      : float
    pressure_ratio  : float        # P_oper / MAWP — debe ser < 1.0

    # Mecanismos Level 1
    gml_status      : str          # General Metal Loss
    lml_status      : str          # Local Metal Loss / pitting
    ssc_status      : str          # SSC / HIC
    creep_status    : str          # Creep
    fatigue_status  : str          # Fatiga térmica

    # Veredicto final
    ffs_status      : str          # PASS / FAIL / MONITOR
    action_required : str
    next_insp_months: int


# ── ENGINE PRINCIPAL ─────────────────────────────────────────
class FFSEngine:
    """
    Evalúa cualquier activo del pipe_static_data.csv
    según API 579-1/ASME FFS-1 Level 1.
    """

    def __init__(self, static_data_path: str, rbi_labels_path: str):
        self.df_static = pd.read_csv(static_data_path)
        self.df_rbi    = pd.read_csv(rbi_labels_path)
        self.df_static.set_index('line_id', inplace=True)

    # ── Carga activo ─────────────────────────────────────────
    def _load_asset(self, tag: str) -> dict:
        if tag not in self.df_static.index:
            raise ValueError(f"Activo {tag} no encontrado")
        row = self.df_static.loc[tag].to_dict()

    # CR y t_estimated desde última ventana del RBI
        rbi_row = self.df_rbi[self.df_rbi['line_id'] == tag]\
                  .sort_values('window').iloc[-1]
        row['cr_mean']    = rbi_row['cr_mean']
        row['RUL_years']  = rbi_row['RUL_years']
        row['pof_cat']    = rbi_row['pof_category']
        row['t_estimated'] = rbi_row['t_estimated']  # ← agregar esta línea
        return row

    # ── 1. Espesor actual estimado ────────────────────────────
    def _calc_thickness(self, a: dict, current_year: int = 2024) -> tuple:
        years_service    = current_year - int(a['install_year'])
        years_since_insp = current_year - int(a['last_inspection_year'])
        # Usar t_estimated del RBI si está disponible
        try:
            t_estimated = float(a['t_estimated'])
            t_actual = t_estimated if t_estimated > 0 else None
        except (KeyError, ValueError, TypeError):
            t_actual = None
        if t_actual is None:
            t_loss   = a['cr_mean'] * years_since_insp
            t_actual = a['nominal_thickness_mm'] - t_loss
        wall_exhausted = t_actual <= a['tmin_mm']
        t_actual       = max(t_actual, 0.0)
        return t_actual, years_service, years_since_insp, wall_exhausted

    # ── 2. MAWP — API 579 Eq. 4.3 (cilindro a presión) ───────
    def _calc_mawp(self, a: dict, t_actual: float) -> float:
        mat   = MATERIAL_PROPS.get(a['material'], MATERIAL_PROPS['CS A106-B'])
        S     = mat['S_mpa']
        E     = 1.0        # joint efficiency — asume radiografía completa
        # Diámetro interior en mm
        if a['asset_type'] == 'vessel':
            R = (a['nominal_diameter_in'] * 25.4) / 2.0
        else:
            # Para pipes: usar tablas ASME B36.10 — aproximación diámetro nominal
            R = (a['nominal_diameter_in'] * 25.4) / 2.0
        # MAWP [MPa] = S*E*t / (R + 0.6*t)  — ASME Sec VIII Div 1 UG-27
        t_c   = t_actual - a['tmin_mm'] * 0.1  # corrosion allowance
        t_c   = max(t_c, 0.5)
        MAWP_mpa = (S * E * t_c) / (R + 0.6 * t_c)
        return MAWP_mpa * 10.0  # convertir a bar

    # ── 3. Espesor mínimo requerido por presión ───────────────
    def _calc_t_required(self, a: dict) -> float:
        mat  = MATERIAL_PROPS.get(a['material'], MATERIAL_PROPS['CS A106-B'])
        S    = mat['S_mpa']
        E    = 1.0
        P    = a['operating_pressure_bar'] / 10.0  # bar → MPa
        R    = (a['nominal_diameter_in'] * 25.4) / 2.0
        # t_req = P*R / (S*E - 0.6*P)
        t_req = (P * R) / (S * E - 0.6 * P)
        return t_req

    # ── 4. MECANISMO: General Metal Loss (API 579 Part 4) ─────
    def _check_gml(self, t_actual: float, t_min: float, t_req: float) -> str:
        """
        Level 1: PASS si t_actual >= max(t_min, t_req) + FCA
        FCA (Future Corrosion Allowance) = 1.0 mm por defecto Level 1
        """
        FCA = 1.0
        if t_actual >= max(t_min, t_req) + FCA:
            return 'PASS'
        elif t_actual >= max(t_min, t_req):
            return 'MONITOR'
        else:
            return 'FAIL'

    # ── 5. MECANISMO: Local Metal Loss / Pitting (API 579 Part 6)
    def _check_lml(self, a: dict, t_actual: float) -> str:
        """
        Level 1 simplificado: evalúa ratio de pérdida localizada
        Asume pitting activo si cr_mean > 0.2 mm/yr y H2S > 200 ppm
        """
        pitting_active = (a['cr_mean'] > 0.2) and (a['h2s_content_ppm'] > 200)
        if not pitting_active:
            return 'PASS'
        # Profundidad estimada de pit (modelo parabolico simplificado)
        years = 2024 - int(a['install_year'])
        pit_depth = 0.5 * a['cr_mean'] * np.sqrt(years)  # mm
        pit_ratio = pit_depth / t_actual if t_actual > 0 else 1.0
        if pit_ratio < 0.2:
            return 'PASS'
        elif pit_ratio < 0.4:
            return 'MONITOR'
        else:
            return 'FAIL'

    # ── 6. MECANISMO: SSC / HIC (API 579 Part 12) ────────────
    def _check_ssc_hic(self, a: dict) -> str:
        """
        Level 1: screening por H2S + temperatura + material
        NACE MR0175 / ISO 15156 umbral: H2S > 50 ppm en fase acuosa
        SSC activo si: ssc_active=1 AND H2S > 50 ppm AND T < 80°C
        HIC activo si: hic_active=1 AND H2S > 50 ppm
        """
        h2s   = a['h2s_content_ppm']
        temp  = a['operating_temp_c']
        ssc   = int(a['ssc_active'])
        hic   = int(a['hic_active'])

        if h2s == 0:
            return 'PASS — sin H2S'
        if ssc and h2s > 50 and temp < 80:
            return 'FAIL — SSC activo (NACE MR0175)'
        if hic and h2s > 50:
            return 'MONITOR — HIC posible, requiere WFMT/RT'
        if h2s > 500:
            return 'MONITOR — H2S severo, inspección NDT especializada'
        return 'PASS'

    # ── 7. MECANISMO: Creep (API 579 Part 10) ────────────────
    def _check_creep(self, a: dict) -> str:
        """
        Level 1: screening por temperatura
        Límite de creep CS (carbono): T > 371°C (700°F)
        Límite alerta temprana: T > 340°C
        """
        T = a['operating_temp_c']
        if T > 371:
            return 'FAIL — zona de creep activo (T > 371°C)'
        elif T > 340:
            return 'MONITOR — zona de alerta creep (340-371°C)'
        else:
            return 'PASS'

    # ── 8. MECANISMO: Fatiga Térmica (API 579 Part 14) ───────
    def _check_fatigue(self, a: dict) -> str:
        """
        Level 1: screening por delta T y ciclos estimados
        Delta T = T_diseño - T_operación como proxy de ciclado térmico
        """
        delta_T = abs(a['design_temp_c'] - a['operating_temp_c'])
        insul   = int(a.get('insulated', 0))

        if delta_T > 150 and not insul:
            return 'FAIL — delta T > 150°C sin aislamiento'
        elif delta_T > 100:
            return 'MONITOR — delta T significativo, evaluar ciclos'
        else:
            return 'PASS'

    # ── 9. VEREDICTO FINAL + intervalo inspección ─────────────
    def _verdict(self, results: list, a: dict,
             t_actual: float, t_min: float,
             wall_exhausted: bool = False) -> tuple:

        # Primero verificar pared agotada
        if wall_exhausted:
            return 'FAIL', 'PARED AGOTADA — reemplazo inmediato requerido', 3, 0.0

        fails    = [r for r in results if 'FAIL' in r]
        monitors = [r for r in results if 'MONITOR' in r]

        # Vida remanente (años hasta t_actual = t_min)
        if a['cr_mean'] > 0:
            rl = (t_actual - t_min) / a['cr_mean']
        else:
            rl = 99.0
        rl = max(round(rl, 1), 0.0)

        if fails:
            status = 'FAIL'
            action = 'Acción inmediata requerida — revisar con ingeniero certificado API 579'
            insp   = 3
        elif monitors:
            status = 'MONITOR'
            action = 'Inspección aumentada — programar NDT en próximos 6 meses'
            insp   = 6
        else:
            insp   = min(24, max(6, int(rl * 12 * 0.5)))
            status = 'PASS'
            action = 'Operable — continuar según plan de inspección RBI'

        return status, action, insp, rl

    # ── MÉTODO PÚBLICO PRINCIPAL ──────────────────────────────
    def assess(self, tag: str, current_year: int = 2024) -> FFSResult:
            a = self._load_asset(tag)
            t_actual, yrs_svc, yrs_insp, wall_exhausted = self._calc_thickness(a, current_year)
            MAWP      = self._calc_mawp(a, t_actual)
            t_req     = self._calc_t_required(a)
            t_margin  = t_actual - max(a['tmin_mm'], t_req)

            gml     = self._check_gml(t_actual, a['tmin_mm'], t_req)
            lml     = self._check_lml(a, t_actual)
            ssc_hic = self._check_ssc_hic(a)
            creep   = self._check_creep(a)
            fatigue = self._check_fatigue(a)

            status, action, insp, rl = self._verdict(
                [gml, lml, ssc_hic, creep, fatigue], a, t_actual, a['tmin_mm'],
                wall_exhausted=wall_exhausted
            )

            return FFSResult(
            tag              = tag,
            asset_type       = a['asset_type'],
            t_nominal_mm     = a['nominal_thickness_mm'],
            t_actual_mm      = round(t_actual, 3),
            t_min_mm         = a['tmin_mm'],
            t_required_mm    = round(t_req, 3),
            t_margin_mm      = round(t_margin, 3),
            remaining_life_yr= rl,
            MAWP_bar         = round(MAWP, 2),
            P_oper_bar       = a['operating_pressure_bar'],
            pressure_ratio   = round(a['operating_pressure_bar'] / MAWP, 3),
            gml_status       = gml,
            lml_status       = lml,
            ssc_status       = ssc_hic,
            creep_status     = creep,
            fatigue_status   = fatigue,
            ffs_status       = status,
            action_required  = action,
            next_insp_months = insp,
        )

    def assess_all(self, current_year: int = 2024) -> pd.DataFrame:
        """Evalúa todos los activos y devuelve DataFrame resumen."""
        results = []
        for tag in self.df_static.index:
            try:
                r = self.assess(tag, current_year)
                results.append({
                    'tag'              : r.tag,
                    'asset_type'       : r.asset_type,
                    't_actual_mm'      : r.t_actual_mm,
                    't_min_mm'         : r.t_min_mm,
                    't_margin_mm'      : r.t_margin_mm,
                    'remaining_life_yr': r.remaining_life_yr,
                    'MAWP_bar'         : r.MAWP_bar,
                    'P_oper_bar'       : r.P_oper_bar,
                    'pressure_ratio'   : r.pressure_ratio,
                    'GML'              : r.gml_status,
                    'LML'              : r.lml_status,
                    'SSC_HIC'          : r.ssc_status,
                    'Creep'            : r.creep_status,
                    'Fatigue'          : r.fatigue_status,
                    'ffs_status'       : r.ffs_status,
                    'action_required'  : r.action_required,
                    'next_insp_months' : r.next_insp_months,
                })
            except Exception as e:
                results.append({'tag': tag, 'ffs_status': f'ERROR: {e}'})
        return pd.DataFrame(results)
    
                # ── MÉTODO: Proximity to Failure Index (PFI) ─────────────
    def calc_pfi(self, tag: str, current_year: int = 2024) -> dict:
            """
            Calcula qué tan cerca está un activo del límite de falla Level 1.
            PFI = 0%  → equipo sano
            PFI = 100% → en el límite exacto de falla
            PFI > 100% → superó el límite (FAIL confirmado)
            
            Tres dimensiones:
            PFI_thickness : pérdida de espesor vs límite t_min
            PFI_mawp      : presión operacional vs MAWP calculado
            PFI_rul       : vida consumida vs vida total estimada
            """
            a        = self._load_asset(tag)
            t_actual, _, _, wall_exhausted = self._calc_thickness(a, current_year)
            MAWP     = self._calc_mawp(a, t_actual)
            r        = self.assess(tag, current_year)

            # ── PFI Espesor ──────────────────────────────────────
            t_nom  = a['nominal_thickness_mm']
            t_min  = a['tmin_mm']
            t_span = t_nom - t_min  # rango total de degradación posible
            if t_span > 0:
                pfi_t = ((t_nom - t_actual) / t_span) * 100
            else:
                pfi_t = 100.0
            pfi_t = round(min(pfi_t, 150.0), 1)  # cap en 150% para display

            # ── PFI Presión (MAWP) ───────────────────────────────
            if MAWP > 0:
                pfi_p = (a['operating_pressure_bar'] / MAWP) * 100
            else:
                pfi_p = 150.0
            pfi_p = round(min(pfi_p, 150.0), 1)

            # ── PFI RUL (vida consumida) ─────────────────────────
            years_total = current_year - int(a['install_year']) + a['RUL_years']
            years_used  = current_year - int(a['install_year'])
            if years_total > 0:
                pfi_rul = (years_used / years_total) * 100
            else:
                pfi_rul = 150.0
            pfi_rul = round(min(pfi_rul, 150.0), 1)

            # ── PFI Final — el peor mecanismo domina ─────────────
            pfi_final = max(pfi_t, pfi_p, pfi_rul)
            dominant  = {pfi_t: 'Pérdida de espesor',
                        pfi_p: 'Presión vs MAWP',
                        pfi_rul: 'Vida útil consumida'}[pfi_final]

            # ── Semáforo ─────────────────────────────────────────
            if pfi_final >= 100:
                level  = 'FAIL'
                color  = '🔴'
            elif pfi_final >= 75:
                level  = 'CRÍTICO'
                color  = '🟠'
            elif pfi_final >= 50:
                level  = 'MONITOR'
                color  = '🟡'
            else:
                level  = 'SAFE'
                color  = '🟢'

            return {
                'tag'           : tag,
                'PFI_thickness' : pfi_t,
                'PFI_mawp'      : pfi_p,
                'PFI_rul'       : pfi_rul,
                'PFI_final'     : round(pfi_final, 1),
                'dominant'      : dominant,
                'level'         : level,
                'color'         : color,
                'ffs_status'    : r.ffs_status,
                'RUL_years'     : a['RUL_years'],
                'action'        : r.action_required,
            }

    def pfi_all(self, current_year: int = 2024) -> pd.DataFrame:
            """PFI para toda la flota — ordenado de mayor a menor riesgo."""
            rows = []
            for tag in self.df_static.index:
                try:
                    rows.append(self.calc_pfi(tag, current_year))
                except Exception as e:
                    rows.append({'tag': tag, 'PFI_final': None,
                                'level': f'ERROR: {e}'})
            df = pd.DataFrame(rows)
            return df.sort_values('PFI_final', ascending=False).reset_index(drop=True)