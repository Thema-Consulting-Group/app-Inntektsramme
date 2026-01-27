
import os
import pandas as pd
from utils import Util

class PostProcess:
    def __init__(self, config_path='config.yaml'):
        base_dir = os.path.dirname(os.path.dirname(__file__))

        # Load config
        self.config = Util.load_config(config_path)

        # Create last run results path if not provided  
        if not self.config['irir_results_path']:
            # Find latest run directory in Results
            results_dir = os.path.join(base_dir, 'Results')
            run_dirs = [d for d in os.listdir(results_dir) if d.startswith('Run_') and os.path.isdir(os.path.join(results_dir, d))]
            if not run_dirs:
                raise FileNotFoundError('No run directories found in Results.')
            latest_run = sorted(run_dirs)[-1]
            results_path = os.path.join(results_dir, latest_run, 'Til inntektsrammeark.xlsx')
        results_path = os.path.join(base_dir, self.config['irir_results_path'])
        results_path = os.path.abspath(results_path)

        # Load results Excel file
        self.irir_results = pd.read_excel(results_path)

        print('Loaded columns:', self.irir_results.columns.tolist())
        print(self.irir_results.head())

        # Assign each column to a self.<column_name> attribute
        self.id_y = self.irir_results['id.y']
        self.orgn = self.irir_results['orgn']
        self.id = self.irir_results['id']
        self.comp = self.irir_results['comp']
        self.rd_cga = self.irir_results['rd_cga']
        self.fp_ld_OPEX = self.irir_results['fp_ld_OPEX']
        self.ld_dep_sf = self.irir_results['ld_dep.sf']
        self.ld_rab_sf = self.irir_results['ld_rab.sf']
        self.ld_RAB = self.irir_results['ld_RAB']
        self.ld_nl = self.irir_results['ld_nl']
        self.ld_cens = self.irir_results['ld_cens']
        self.fp_rd_OPEX = self.irir_results['fp_rd_OPEX']
        self.rd_dep_sf = self.irir_results['rd_dep.sf']
        self.rd_rab_sf = self.irir_results['rd_rab.sf']
        self.rd_RAB = self.irir_results['rd_RAB']
        self.rd_nl = self.irir_results['rd_nl']
        self.rd_cens = self.irir_results['rd_cens']
        self.fp_t_OPEX = self.irir_results['fp_t_OPEX']
        self.t_dep_sf = self.irir_results['t_dep.sf']
        self.t_rab_sf = self.irir_results['t_rab.sf']
        self.t_cens = self.irir_results['t_cens']
        self.pnl_rc = self.irir_results['pnl.rc']
        self.ap_t_2 = self.irir_results['ap.t_2']
        self.ld_eff_OOTO = self.irir_results['ld_eff.OOTO']
        self.rd_eff_OOTO = self.irir_results['rd_eff.OOTO']
        self.ld_eff_s2_cb = self.irir_results['ld_eff.s2.cb']
        self.rd_eff_s2_cb = self.irir_results['rd_eff.s2.cb']



        print(self.id)


if __name__ == "__main__":
    post = PostProcess()
    
