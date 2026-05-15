# ============================================================
# ffs_engine.py  —  API 579-1/ASME FFS-1  Level 1
# Motor de evaluación Fitness-for-Service
# TWIN-RBI Mongstad  —  AIM Consulting
# Soporta: pipes, vessels, exchangers
# ============================================================

import numpy as np
import pandas as pd
from dataclasses import dataclass
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
    tag              : str
    asset_type       : str
    t_nominal_mm     : float
    t_actual_mm      : float
    t_min_mm         : float
    t_required_mm    : float
    t_margin_mm      : float
    remaining_life_yr: float
    MAWP_bar         : float
    P_oper_bar       : float
    pressure_ratio   : float
    gml_status       : str
    lml_status       : str
    ssc_status       : str
    creep_status     : str
    fatigue_status   : str
    ffs_status       : str
    action_required  : str
    next_insp_months : int


# ── ENGINE PRINCIPAL ──────────────────────────────────────────
class FFSEngine:

    def __init__(self, static_data_path: str, rbi_labels_path: str):
        self.df_static = pd.read_csv(static_data_path)
        self.df_rbi    = pd.read_csv(rbi_labels_path)
        self.df_static.set_index('line_id', inplace=True)

    def _load_asset(self, tag: str) -> dict:
        if tag not in self.df_static.index:
            raise ValueError(f"Activo {tag} no encontrado")
        row = self.df_static.loc[tag].to_dict()
        rbi_row = self.df_rbi[self.df_rbi['line_id'] == tag]\
                      .sort_values('window').iloc[-1]
        row['cr_mean']     = rbi_row['cr_mean']
        row['RUL_years']   = rbi_row['RUL_years']
        row['pof_cat']     = rbi_row['pof_category']
        row['t_estimated'] = rbi_row['t_estimated']
        return row

    def _calc_thickness(self, a: dict, current_year: int = 2024) -> tuple:
        years_service    = current_year - int(a['install_year'])
        years_since_insp = current_year - int(a['last_inspection_year'])
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

    def _calc_mawp(self, a: dict, t_actual: float) -> float:
        mat      = MATERIAL_PROPS.get(a['material'], MATERIAL_PROPS['CS A106-B'])
        S        = mat['S_mpa']
        E        = 1.0
        R        = (a['nominal_diameter_in'] * 25.4) / 2.0
        t_c      = max(t_actual - a['tmin_mm'] * 0.1, 0.5)
        MAWP_mpa = (S * E * t_c) / (R + 0.6 * t_c)
        return MAWP_mpa * 10.0

    def _calc_t_required(self, a: dict) -> float:
        mat   = MATERIAL_PROPS.get(a['material'], MATERIAL_PROPS['CS A106-B'])
        S     = mat['S_mpa']
        P     = a['operating_pressure_bar'] / 10.0
        R     = (a['nominal_diameter_in'] * 25.4) / 2.0
        t_req = (P * R) / (S * 1.0 - 0.6 * P)
        return t_req

    def _check_gml(self, t_actual: float, t_min: float, t_req: float) -> str:
        FCA = 1.0
        if t_actual >= max(t_min, t_req) + FCA:
            return 'PASS'
        elif t_actual >= max(t_min, t_req):
            return 'MONITOR'
        else:
            return 'FAIL'

    def _check_lml(self, a: dict, t_actual: float) -> str:
        pitting_active = (a['cr_mean'] > 0.2) and (a['h2s_content_ppm'] > 200)
        if not pitting_active:
            return 'PASS'
        years     = 2024 - int(a['install_year'])
        pit_depth = 0.5 * a['cr_mean'] * np.sqrt(years)
        pit_ratio = pit_depth / t_actual if t_actual > 0 else 1.0
        if pit_ratio < 0.2:
            return 'PASS'
        elif pit_ratio < 0.4:
            return 'MONITOR'
        else:
            return 'FAIL'

    def _check_ssc_hic(self, a: dict) -> str:
        h2s  = a['h2s_content_ppm']
        temp = a['operating_temp_c']
        ssc  = int(a['ssc_active'])
        hic  = int(a['hic_active'])
        if h2s == 0:
            return 'PASS — sin H2S'
        if ssc and h2s > 50 and temp < 80:
            return 'FAIL — SSC activo (NACE MR0175)'
        if hic and h2s > 50:
            return 'MONITOR — HIC posible, requiere WFMT/RT'
        if h2s > 500:
            return 'MONITOR — H2S severo, inspeccion NDT especializada'
        return 'PASS'

    def _check_creep(self, a: dict) -> str:
        T = a['operating_temp_c']
        if T > 371:
            return 'FAIL — zona de creep activo (T > 371C)'
        elif T > 340:
            return 'MONITOR — zona de alerta creep (340-371C)'
        else:
            return 'PASS'

    def _check_fatigue(self, a: dict) -> str:
        delta_T = abs(a['design_temp_c'] - a['operating_temp_c'])
        insul   = int(a.get('insulated', 0))
        if delta_T > 150 and not insul:
            return 'FAIL — delta T > 150C sin aislamiento'
        elif delta_T > 100:
            return 'MONITOR — delta T significativo, evaluar ciclos'
        else:
            return 'PASS'

    def _verdict(self, results: list, a: dict,
                 t_actual: float, t_min: float,
                 wall_exhausted: bool = False) -> tuple:
        if wall_exhausted:
            return 'FAIL', 'PARED AGOTADA — reemplazo inmediato requerido', 3, 0.0
        fails    = [r for r in results if 'FAIL' in r]
        monitors = [r for r in results if 'MONITOR' in r]
        if a['cr_mean'] > 0:
            rl = (t_actual - t_min) / a['cr_mean']
        else:
            rl = 99.0
        rl = max(round(rl, 1), 0.0)
        if fails:
            return 'FAIL', 'Accion inmediata requerida — revisar con ingeniero certificado API 579', 3, rl
        elif monitors:
            return 'MONITOR', 'Inspeccion aumentada — programar NDT en proximos 6 meses', 6, rl
        else:
            insp = min(24, max(6, int(rl * 12 * 0.5)))
            return 'PASS', 'Operable — continuar segun plan de inspeccion RBI', insp, rl

    def assess(self, tag: str, current_year: int = 2024) -> FFSResult:
        a = self._load_asset(tag)
        t_actual, yrs_svc, yrs_insp, wall_exhausted = self._calc_thickness(a, current_year)
        MAWP     = self._calc_mawp(a, t_actual)
        t_req    = self._calc_t_required(a)
        t_margin = t_actual - max(a['tmin_mm'], t_req)
        gml      = self._check_gml(t_actual, a['tmin_mm'], t_req)
        lml      = self._check_lml(a, t_actual)
        ssc_hic  = self._check_ssc_hic(a)
        creep    = self._check_creep(a)
        fatigue  = self._check_fatigue(a)
        status, action, insp, rl = self._verdict(
            [gml, lml, ssc_hic, creep, fatigue], a, t_actual, a['tmin_mm'],
            wall_exhausted=wall_exhausted
        )
        return FFSResult(
            tag               = tag,
            asset_type        = a['asset_type'],
            t_nominal_mm      = a['nominal_thickness_mm'],
            t_actual_mm       = round(t_actual, 3),
            t_min_mm          = a['tmin_mm'],
            t_required_mm     = round(t_req, 3),
            t_margin_mm       = round(t_margin, 3),
            remaining_life_yr = rl,
            MAWP_bar          = round(MAWP, 2),
            P_oper_bar        = a['operating_pressure_bar'],
            pressure_ratio    = round(a['operating_pressure_bar'] / MAWP, 3),
            gml_status        = gml,
            lml_status        = lml,
            ssc_status        = ssc_hic,
            creep_status      = creep,
            fatigue_status    = fatigue,
            ffs_status        = status,
            action_required   = action,
            next_insp_months  = insp,
        )

    def assess_all(self, current_year: int = 2024) -> pd.DataFrame:
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

    def calc_pfi(self, tag: str, current_year: int = 2024) -> dict:
        a        = self._load_asset(tag)
        t_actual, _, _, wall_exhausted = self._calc_thickness(a, current_year)
        MAWP     = self._calc_mawp(a, t_actual)
        r        = self.assess(tag, current_year)
        t_nom    = a['nominal_thickness_mm']
        t_min    = a['tmin_mm']
        t_span   = t_nom - t_min
        pfi_t    = round(min(((t_nom - t_actual) / t_span) * 100 if t_span > 0 else 100.0, 150.0), 1)
        pfi_p    = round(min((a['operating_pressure_bar'] / MAWP) * 100 if MAWP > 0 else 150.0, 150.0), 1)
        years_total = current_year - int(a['install_year']) + a['RUL_years']
        years_used  = current_year - int(a['install_year'])
        pfi_rul  = round(min((years_used / years_total) * 100 if years_total > 0 else 150.0, 150.0), 1)
        pfi_final = max(pfi_t, pfi_p, pfi_rul)
        dominant  = {pfi_t: 'Perdida de espesor',
                     pfi_p: 'Presion vs MAWP',
                     pfi_rul: 'Vida util consumida'}[pfi_final]
        if pfi_final >= 100:
            level, color = 'FAIL',    '🔴'
        elif pfi_final >= 75:
            level, color = 'CRITICO', '🟠'
        elif pfi_final >= 50:
            level, color = 'MONITOR', '🟡'
        else:
            level, color = 'SAFE',    '🟢'
        return {
            'tag'          : tag,
            'PFI_thickness': pfi_t,
            'PFI_mawp'     : pfi_p,
            'PFI_rul'      : pfi_rul,
            'PFI_final'    : round(pfi_final, 1),
            'dominant'     : dominant,
            'level'        : level,
            'color'        : color,
            'ffs_status'   : r.ffs_status,
            'RUL_years'    : a['RUL_years'],
            'action'       : r.action_required,
        }

    def pfi_all(self, current_year: int = 2024) -> pd.DataFrame:
        rows = []
        for tag in self.df_static.index:
            try:
                rows.append(self.calc_pfi(tag, current_year))
            except Exception as e:
                rows.append({'tag': tag, 'PFI_final': None, 'level': f'ERROR: {e}'})
        df = pd.DataFrame(rows)
        return df.sort_values('PFI_final', ascending=False).reset_index(drop=True)
