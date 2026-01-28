
import os
import pandas as pd #type: ignore
from utils import Util
pd.set_option('display.float_format', '{:.2f}'.format)

class IRData_postprocess:
    def __init__(self, config_path='config.yaml'):
        base_dir: str = os.path.dirname(os.path.dirname(__file__))

        # Load config
        self.config: dict = Util.load_config(config_path)

        # Load results Excel file
        # Create last run results path if not provided   
        if not self.config['irir_results_path']:
            # Find latest run directory in Results
            results_dir: str = os.path.join(base_dir, 'Results')
            run_dirs: list[str] = [d for d in os.listdir(results_dir) if d.startswith('Run_') and os.path.isdir(os.path.join(results_dir, d))]
            if not run_dirs:
                raise FileNotFoundError('No run directories found in Results.')
            latest_run: str = sorted(run_dirs)[-1]
            results_path: str = os.path.join(results_dir, latest_run, 'Til inntektsrammeark.xlsx')
        
        #If it is defined in config, use that path
        else:
            results_path: str = os.path.join(base_dir, self.config['irir_results_path'])
        results_path = os.path.abspath(results_path)
        self.irir_results: pd.DataFrame = pd.read_excel(results_path)

        # Assign each column to a self.<column_name> attribute
        self.id_y: pd.Series = self.irir_results['id.y']
        self.orgn: pd.Series = self.irir_results['orgn']
        self.id: pd.Series = self.irir_results['id']
        self.comp: pd.Series = self.irir_results['comp']
        self.rd_cga: pd.Series = self.irir_results['rd_cga']
        self.fp_ld_OPEX: pd.Series = self.irir_results['fp_ld_OPEX']
        self.ld_dep_sf: pd.Series = self.irir_results['ld_dep.sf']
        self.ld_rab_sf: pd.Series = self.irir_results['ld_rab.sf']
        self.ld_RAB: pd.Series = self.irir_results['ld_RAB']
        self.ld_nl: pd.Series = self.irir_results['ld_nl']
        self.ld_cens: pd.Series = self.irir_results['ld_cens']
        self.fp_rd_OPEX: pd.Series = self.irir_results['fp_rd_OPEX']
        self.rd_dep_sf: pd.Series = self.irir_results['rd_dep.sf']
        self.rd_rab_sf: pd.Series = self.irir_results['rd_rab.sf']
        self.rd_RAB: pd.Series = self.irir_results['rd_RAB']
        self.rd_nl: pd.Series = self.irir_results['rd_nl']
        self.rd_cens: pd.Series = self.irir_results['rd_cens']
        self.fp_t_OPEX: pd.Series = self.irir_results['fp_t_OPEX']
        self.t_dep_sf: pd.Series = self.irir_results['t_dep.sf']
        self.t_rab_sf: pd.Series = self.irir_results['t_rab.sf']
        self.t_cens: pd.Series = self.irir_results['t_cens']
        self.pnl_rc: pd.Series = self.irir_results['pnl.rc']
        self.ap_t_2: pd.Series = self.irir_results['ap.t_2']
        self.ld_eff_OOTO: pd.Series = self.irir_results['ld_eff.OOTO']
        self.rd_eff_OOTO: pd.Series = self.irir_results['rd_eff.OOTO']
        self.ld_eff_s2_cb: pd.Series = self.irir_results['ld_eff.s2.cb']
        self.rd_eff_s2_cb: pd.Series = self.irir_results['rd_eff.s2.cb']

        #Forutsetninger
        kpi_2026: float = self.config['forutsetninger']['kpi_justering'][2026]
        kpi_2024: float = self.config['forutsetninger']['kpi_justering'][2024]
        self.t_over_t_2_kpi: float = kpi_2026 / kpi_2024

        aarslonn_2024: float = self.config['forutsetninger']['aarslonn'][2024]
        aarslonn_2026: float = self.config['forutsetninger']['aarslonn'][2026]
        self.t_over_t_2_aarslonn: float = aarslonn_2026 / aarslonn_2024
        
    def calc_referanserente(self):
        # r = (1 - G) x (Rf + Infl + βe x MP)/(1 - s) + G x (Swap + KP)
        finance_param = self.config['forutsetninger']['finansparametere']
        referanserente = (1 - finance_param['gjeldsandel']) * ( finance_param['noytral_realrente'] + finance_param['inflasjon'] +
            (finance_param['ek-beta'] * finance_param['markedspremie'])) / (1 - finance_param['skatt']) + finance_param['gjeldsandel'] * (finance_param['swap'] + finance_param['kredittpremie'])
        referanserente = referanserente / 100.0

        return referanserente 
    
    def calc_total_drift_og_vedlikholdskostnader(self):
        """ Calculate total DV """ 
        total_drift_og_vedlikholdskostnader = self.fp_ld_OPEX + self.fp_rd_OPEX + self.fp_t_OPEX
        total_drift_og_vedlikeholdskostander_incl_utredrningsansvar = total_drift_og_vedlikholdskostnader + self.rd_cga
        return total_drift_og_vedlikholdskostnader, total_drift_og_vedlikeholdskostander_incl_utredrningsansvar

    def calc_avskrining(self):
        avskrivninger = self.ld_dep_sf + self.rd_dep_sf + self.t_dep_sf
        return avskrivninger

    def calc_avkastningsgrunnlag(self):
        avkastningsgrunnlag = self.ld_rab_sf + self.rd_rab_sf + self.t_rab_sf
        return avkastningsgrunnlag

    def calc_bokforte_verdier(self):
        bokforte_verider = (self.calc_avkastningsgrunnlag() / 1.01).round(0).astype(int)
        return bokforte_verider
            
    def calc_krafttap_i_dnett(self):
        return self.ld_nl

    def calc_krafttap_i_rnett(self):
        return self.rd_nl

    def calc_kile(self):
        return self.ld_cens + self.rd_cens + self.t_cens

    def calc_ld_aarlonnjusterte_d_v_kostnader(self):
        return  self.fp_ld_OPEX * self.t_over_t_2_aarslonn 

    def calc_ld_nettapskostnader(self):
        return self.ld_nl * self.pnl_rc

    def calc_ld_sum_kostnader(self):
        return (self.calc_ld_aarlonnjusterte_d_v_kostnader() + 
                self.ld_dep_sf + 
                self.calc_ld_nettapskostnader() + 
                (self.ld_cens * self.t_over_t_2_kpi)) 

    def calc_ld_kostnadsgrunnlag(self):
        return (self.calc_ld_sum_kostnader() + self.ld_rab_sf * self.calc_referanserente()) 

    def calc_rd_aarslonnjusterte_d_v_kostnader_excl_utredningskostnader(self):
        return self.fp_rd_OPEX * self.t_over_t_2_aarslonn

    def calc_rd_nettapskostndaer(self):
        return self.rd_nl * self.pnl_rc


    def calc_rd_kostnadsgrunnlag(self):
        #=AI4+Y4*Forutsetninger!$C$32+U4+V4*Forutsetninger!$B$6
        return (self.calc_rd_aarslonnjusterte_d_v_kostnader_excl_utredningskostnader() + 
            self.rd_cens*self.t_over_t_2_aarslonn + 
            + self.rd_dep_sf + self.rd_rab_sf * self.calc_referanserente())


    def calc_transmisjonsnett_kostnadsgrunnlag(self):
        # =(Z4*Forutsetninger!$C$38)+AA4+(AB4*Forutsetninger!$B$6)+(AC4*Forutsetninger!$C$32) 
        return (
            self.fp_t_OPEX * self.t_over_t_2_aarslonn +
            self.t_dep_sf +
            self.t_rab_sf * self.calc_referanserente() +
            self.t_cens * self.t_over_t_2_kpi)

    def create_IR_DataFrame(self):
        # Calculate columns using methods where required
        total_dv, total_dv_incl_utred = self.calc_total_drift_og_vedlikholdskostnader()
        avskrivninger = self.calc_avskrining()
        avkastningsgrunnlag = self.calc_avkastningsgrunnlag()
        bokforte_verdier = self.calc_bokforte_verdier()
        krafttap_dnett = self.calc_krafttap_i_dnett()
        krafttap_rnett = self.calc_krafttap_i_rnett()
        kile = self.calc_kile()
        aarlonnjusterte_dv_ld = self.calc_ld_aarlonnjusterte_d_v_kostnader()
        nettapskostnad_ld = self.calc_ld_nettapskostnader()
        sum_kostnader = self.calc_ld_sum_kostnader()
        kostnadsgrunnlag_ld = self.calc_ld_kostnadsgrunnlag()
        aarslonnjusterte_dv_rd = self.calc_rd_aarslonnjusterte_d_v_kostnader_excl_utredningskostnader()
        nettapskostnad_rd =self.calc_rd_nettapskostndaer()
        kostnadsgrunnlag_rd = self.calc_rd_kostnadsgrunnlag()
        kostnadsgrunnlag_t = self.calc_transmisjonsnett_kostnadsgrunnlag()

        # Compose DataFrame with exact column names and order from CSV
        data = {
            'Org.nr': self.orgn,
            'ID': self.id,
            'Selskap': self.comp,
            'År': 2024,
            'DV inkl.utrednings-ansvar': total_dv_incl_utred,
            'Kostnader knyttet til utrednings- og koordineringsansvar': self.rd_cga,
            'DV uten kostnader knyttet til utrednings-ansvar': total_dv,
            'Avskrivninger': avskrivninger,
            'Bokførte verdier': bokforte_verdier,
            'Avkastningsgrunnlag': avkastningsgrunnlag,
            'Krafttap MWh i Dnett': krafttap_dnett,
            'Krafttap MWh i Rnett': krafttap_rnett,
            'Kile': kile,
            'Lokalt D&V-kostnader': self.fp_ld_OPEX,
            'Lokalt AVS': self.ld_dep_sf,
            'Lokalt AKG inkl 1% arbeids-kapital': self.ld_rab_sf,
            'Lokalt AKG inkl 17b': self.ld_RAB,
            'Lokalt Nettap MWh': self.ld_nl,
            'Lokalt KILE (fq)': self.ld_cens,
            'Regionalt D&V-kostnader uten utredningskostnader': self.fp_rd_OPEX,
            'Regionalt AVS': self.rd_dep_sf,
            'Regionalt AKG inkl 17b': self.rd_RAB,
            'Regionalt Nettap MWh': self.rd_nl,
            'Regionalt KILE (fq)': self.rd_cens,
            'Transmisjonsnett D&V-kostnader': self.fp_t_OPEX,
            'Transmisjonsnett AVS': self.t_dep_sf,
            'Transmisjonsnett AKG inkl 1% arbeids-kapital': self.t_rab_sf,
            'Transmisjonsnett KILE (fq)': self.t_cens,
            'Kraftpris 2026': self.pnl_rc,
            'Lokalt Årslønnjusterte D&V-kostnader': aarlonnjusterte_dv_ld,
            'Lokalt Nettapskostnad': nettapskostnad_ld,
            'Lokalt Sum kostnader': sum_kostnader,
            'Lokalt Kostnadsgrunnlag': kostnadsgrunnlag_ld,
            'Regionalt Årslønnjusterte D&V-kostnader uten utredningskostnader': aarslonnjusterte_dv_rd,
            'Regionalt Nettapskostnad': nettapskostnad_rd,
            'Regionalt Kostnadsgrunnlag ': kostnadsgrunnlag_rd,
            'Transmisjonsnett Kostnadsgrunnlag': kostnadsgrunnlag_t,
        }
 
        df = pd.DataFrame(data)
        return df

class ETL(IRData_postprocess):
    def __init__(self):
        super().__init__()
        self.ir_df = IRData_postprocess().create_IR_DataFrame()
        self.d_v_kostnader_eks_utredningskostnad = self.ir_df[ 'DV uten kostnader knyttet til utrednings-ansvar']
        self.avskrivninger = self.ir_df['Avskrivninger']
        self.bokforte_verdier = self.ir_df['Bokførte verdier']
        self.avkasntningsgrunnlag = self.ir_df['Avkastningsgrunnlag']
        self.nettap_mwh_ld = self.ir_df['Krafttap MWh i Dnett']
        self.nettap_mwh_rd = self.ir_df['Krafttap MWh i Rnett']
        self.nettapskostnad_ld = self.ir_df['Lokalt Nettapskostnad']
        self.nettapskostnad_rd = self.ir_df['Regionalt Nettapskostnad']
        self.kile = self.ir_df['Kile']

    def calc_aarslonnjusterte_d_v_kostnader(self):
        return self.d_v_kostnader_eks_utredningskostnad * self.t_over_t_2_aarslonn

    def calc_kpi_justert_kile(self):
        return self.kile * self.t_over_t_2_kpi

    def create_ETL_DataFrame(self):
        data: pd.DataFrame = {
            'Org.nr': self.orgn,
            'ID': self.id,
            'Selskap': self.comp,
            'inntektsramme 2026': None,
            'D&V-kostnader eks utredningskostnader': self.d_v_kostnader_eks_utredningskostnad,
            'Årslønn-justerte D&V-kostnader eks utredningskostnader': self.calc_aarslonnjusterte_d_v_kostnader(),
            'AVS': self.avskrivninger,
            'BFV': self.bokforte_verdier,
            'AKG (inkl 1 % arbeids-kapital)': self.avkasntningsgrunnlag,
            'Nettap MWh i LD': self.nettap_mwh_ld,
            'Nettap MWh i RD': self.nettap_mwh_rd,
            'Nettaps- kostnad i LD': self.nettapskostnad_ld,
            'Nettaps- kostnad i RD': self.nettapskostnad_rd,
            'KILE': self.kile,
            'KPI-justert KILE': self.calc_kpi_justert_kile(),
            'Årslønn-justerte kostnader knyttet til utred.ansvar og KDS': self.rd_cga,
            'Sum kostnader': self.calc_aarslonnjusterte_d_v_kostnader() + self.avskrivninger + self.nettapskostnad_ld + self.nettapskostnad_rd + self.calc_kpi_justert_kile()  + self.rd_cga, 
            'Kostnadsgrunnlag': self.calc_aarslonnjusterte_d_v_kostnader() + self.avskrivninger + self.nettapskostnad_ld + self.nettapskostnad_rd + self.calc_kpi_justert_kile()  + self.rd_cga + self.avkasntningsgrunnlag * self.calc_referanserente()  
            }

        df: pd.DataFrame = pd.DataFrame(data)
        print(df)
        return df

if __name__ == "__main__":
    post = IRData_postprocess()
    ir_df = post.create_IR_DataFrame()
    ir_df.to_csv('PostProcessed_Inntektsrammer.csv', sep = ';', index=False)

    data = ETL()
    data.create_ETL_DataFrame()

