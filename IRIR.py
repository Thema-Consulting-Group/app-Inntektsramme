#!/usr/bin/env python3
"""
IRiR Orchestrator - Python version of IRiR.R
Revenue cap calculation orchestration in Python
"""

import os
import sys
import subprocess
import time
from datetime import datetime
from pathlib import Path

# Try to import rpy2 with fallback to subprocess
try:
    import rpy2.robjects as ro
    from rpy2.robjects import conversion, default_converter
    from rpy2.robjects.packages import importr
    HAS_RPY2 = True
except ImportError as e:
    print(f"Warning: rpy2 not available ({e}). Falling back to subprocess mode.")
    HAS_RPY2 = False

class IRiROrchestrator:
    def __init__(self, base_path=None):
        """Initialize the IRiR Orchestrator"""
        self.start_time = time.time()
        self.base_path = Path(base_path) if base_path else Path(__file__).parent
        self.results_dir = self.base_path / "Results"
        self.timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        self.run_dir = self.results_dir / f"Run_{self.timestamp}"
        
        # Bootstrap settings
        self.BS_new = 0
        self.BS_ite = 100000
        
        # Calculation type for storage in DWH
        self.versjon = 2  # 0=Other, 1=Preliminary, 2=Notice, 3=Decision, 4=After complaint (prelim), 5=After complaint (final)
        
        # Set up R interface mode
        self.use_rpy2 = HAS_RPY2
        
        # Setup conversion context if rpy2 is available
        if self.use_rpy2:
            try:
                from rpy2.robjects import pandas2ri
                self.converter = default_converter + pandas2ri.converter
            except Exception as e:
                print(f"Warning: pandas2ri conversion failed ({e}). Using basic conversion.")
                self.converter = default_converter
        else:
            # Find R executable for subprocess mode
            self.r_executable = self._find_r_executable()
        
    def _find_r_executable(self):
        """Find R executable on the system"""
        # Common R installation paths on Windows
        r_paths = [
            r"C:\Users\jp117\AppData\Local\Programs\R\R-4.5.2\bin\Rscript.exe",
            r"C:\Program Files\R\R-4.5.2\bin\Rscript.exe",
            r"C:\Program Files (x86)\R\R-4.5.2\bin\Rscript.exe",
        ]
        
        for r_path in r_paths:
            if os.path.exists(r_path):
                return r_path
                
        # Try to find in PATH
        import shutil
        r_exe = shutil.which("Rscript")
        if r_exe:
            return r_exe
            
        raise FileNotFoundError("R executable not found. Please install R or add it to PATH.")
    
    def _setup_r_packages(self):
        """One-time setup and installation of R packages"""
        print("Setting up R packages...")
        
        # Create package setup script
        package_setup_script = self.base_path / "temp_package_setup.R"
        setup_code = '''
            # Set CRAN mirror and options
            options(repos = c(CRAN = "https://cran.rstudio.com/"))
            options(scipen = 2000)

            # Install/load required R packages
            packages <- c("Benchmarking", "plyr", "dplyr", "openxlsx", "rstudioapi", "tidyverse", "writexl", "readxl")

            for (pkg in packages) {
                if (!pkg %in% installed.packages()) {
                    cat("Installing package:", pkg, "\n")
                    install.packages(pkg)
                }
                library(pkg, character.only = TRUE)
            }
            
            cat("All packages loaded successfully\n")
        '''
        
        with open(package_setup_script, 'w') as f:
            f.write(setup_code)
            
        result = subprocess.run([self.r_executable, str(package_setup_script)], 
                              capture_output=True, text=True, cwd=str(self.base_path))
        
        package_setup_script.unlink()
        
        if result.returncode != 0:
            print(f"Package setup failed: {result.stderr}")
            raise RuntimeError(f"Package setup failed: {result.stderr}")
            
        print("✓ R packages ready")
    
    def setup_r_environment(self):
        """Set up R environment - equivalent to R setup in IRiR.R"""
        print("Setting up R environment...")
        
        # Create results directory
        os.makedirs(self.run_dir, exist_ok=True)
        
        # Setup packages once
        self._setup_r_packages()
        
        # Create initial workspace with environment variables
        workspace_setup_script = self.base_path / "temp_workspace_setup.R"
        workspace_file = str(self.base_path / "temp_workspace.RData").replace(chr(92), "/")
        
        setup_code = f'''
            # Set working directory
            setwd("{str(self.base_path).replace(chr(92), "/")}")
            
            # Load packages (already installed)
            packages <- c("Benchmarking", "plyr", "dplyr", "openxlsx", "rstudioapi", "tidyverse", "writexl", "readxl")
            for (pkg in packages) {{
                library(pkg, character.only = TRUE)
            }}

            # Set global variables
            BS.new <- {self.BS_new}
            BS.ite <- {self.BS_ite}
            Statnett_calc <- FALSE
            run_dir <- "{str(self.run_dir).replace(chr(92), "/")}"
            results_dir <- "{str(self.results_dir).replace(chr(92), "/")}"
            
            # Load prerequisites (equivalent to loading forutsetninger.Rdata)
            forutsetninger_file <- "./Data/forutsetninger.Rdata"
            if (file.exists(forutsetninger_file)) {{
                load(file = forutsetninger_file)
                cat("Loaded forutsetninger.Rdata\\n")
            }} else {{
                cat("Warning: forutsetninger.Rdata not found\\n")
            }}

            # Save initial workspace
            save.image("{workspace_file}")
            
            cat("R environment ready\\n")
            cat("Working directory:", getwd(), "\\n")
            cat("Results directory:", run_dir, "\\n")
        '''
        
        with open(workspace_setup_script, 'w') as f:
            f.write(setup_code)
            
        result = subprocess.run([self.r_executable, str(workspace_setup_script)], 
                              capture_output=True, text=True, cwd=str(self.base_path))
        
        workspace_setup_script.unlink()
        
        if result.returncode != 0:
            print(f"Environment setup failed: {result.stderr}")
            raise RuntimeError(f"Environment setup failed: {result.stderr}")
            
        print("✓ R environment ready")
        print(f"✓ Results will be saved to: {self.run_dir}")
        
    def run_r_script(self, script_path, description=""):
        """Execute an R script using subprocess"""
        script_file = self.base_path / script_path
        
        if not script_file.exists():
            raise FileNotFoundError(f"R script not found: {script_file}")
            
        print(f"Running: {script_path} - {description}")
        
        # Create wrapper script that sources the target script
        wrapper_script = self.base_path / "temp_wrapper.R"
        workspace_file = str(self.base_path / "temp_workspace.RData").replace(chr(92), "/")
        
        wrapper_code = f'''
            # Set working directory
            setwd("{str(self.base_path).replace(chr(92), "/")}")

            # Load required packages (libraries don't persist in workspace saves)
            packages <- c("Benchmarking", "plyr", "dplyr", "openxlsx", "rstudioapi", "tidyverse", "writexl", "readxl")
            for (pkg in packages) {{
                library(pkg, character.only = TRUE)
            }}

            # Load workspace (variables and data)
            if (file.exists("{workspace_file}")) {{
                load("{workspace_file}")
                cat("Loaded workspace\\n")
            }} else {{
                cat("Error: Workspace file not found\\n")
                quit(status = 1)
            }}

            # Source the target script
            tryCatch({{
                source("{script_path}")
                cat("Script completed successfully\\n")
                
                # Save workspace for next script
                save.image("{workspace_file}")
                cat("Saved workspace for next script\\n")
                
            }}, error = function(e) {{
                cat("Error in script:", conditionMessage(e), "\\n")
                quit(status = 1)
            }})
        '''
        
        with open(wrapper_script, 'w') as f:
            f.write(wrapper_code)
            
        try:
            result = subprocess.run([self.r_executable, str(wrapper_script)], 
                                  capture_output=True, text=True, cwd=str(self.base_path))
            
            # Clean up temp file
            wrapper_script.unlink()
            
            if result.returncode != 0:
                print(f"✗ Error in {script_path}:")
                print(f"STDOUT: {result.stdout}")
                print(f"STDERR: {result.stderr}")
                raise RuntimeError(f"R script failed: {script_path}")
                
            print(f"✓ Completed: {script_path}")
            
        except Exception as e:
            # Clean up temp file on error
            if wrapper_script.exists():
                wrapper_script.unlink()
            raise
    
    def run_analysis_pipeline(self):
        """Run the complete IRiR analysis pipeline"""
        print("="*60)
        print("IRiR Revenue Cap Calculation Pipeline")
        print("="*60)
        
        try:
            # Setup
            self.setup_r_environment()
            
            # Stage 0: Functions and data preparation
            self.run_r_script("R-script/functions_nve.R", "NVE utility functions")
            self.run_r_script("R-script/0_1_Config_Assumptions_Data.R", "Configuration and data import")
            self.run_r_script("R-script/0_2_Merging_Z-variables.R", "Merging Z-variables")
            
            # Export base data using R script
            export_script = self.base_path / "temp_export.R"
            workspace_file = str(self.base_path / "temp_workspace.RData").replace(chr(92), "/")
            
            export_code = f'''
                # Set working directory
                setwd("{str(self.base_path).replace(chr(92), "/")}")

                # Load packages
                library(writexl)
                library(openxlsx)

                # Load workspace
                if (file.exists("{workspace_file}")) {{
                    load("{workspace_file}")
                    cat("Loaded workspace\\n")
                }} else {{
                    cat("Error: Workspace file not found\\n")
                    quit(status = 1)
                }}

                # Set variables
                run_dir <- "{str(self.run_dir).replace(chr(92), "/")}"

                # Export base data
                write.dat = dat[,c("orgn", "y", "comp", "ld_OPEXxS", "ld_sal", "ld_sal.cap", "ld_pens", 
                                "ld_pens.eq", "ld_impl", "ld_391", "ld_elhub", "ld_usla", "rd_OPEXxS",
                                "rd_sal", "rd_sal.cap", "rd_pens", "rd_pens.eq", "rd_impl", "rd_391", 
                                "rd_elhub", "rd_cga", "rd_usla", "t_OPEXxS", "t_sal", "t_sal.cap",
                                "t_pens", "t_pens.eq", "t_impl", "t_391", "t_elhub", "ld_bv.sf", 
                                "ld_dep.sf", "ld_bv.gf", "ld_dep.gf", "rd_bv.sf", "rd_dep.sf", 
                                "rd_bv.gf", "rd_dep.gf", "t_bv.sf", "t_dep.sf", "ld_cens", "rd_cens", 
                                "t_cens", "ld_nl", "rd_nl", "ld_sub", "ld_hvoh", "ld_hvug", "ld_hvsc", 
                                "ld_hv", "ld_ss", "rd_wv.ol", "rd_wv.uc", "rd_wv.sc", "rd_wv.ss",
                                "ldz_salt", "ldz_coast_wind", "ldz_water", "ldz_incline", "ldz_prod",
                                "ldz_snow_trees", "ldz_forest_broadleaf", "ldz_snowdrift", "ldz_snow_400", 
                                "ldz_wind_99", "ldz_frosthours", "ldz_forest_mixed_conf", "ldz_mgc", 
                                "ap.t_2", "pnl.rc")]

                csv_file = file.path(run_dir, paste0(Sys.Date(), "_grunnlagsdata.csv"))
                xlsx_file = file.path(run_dir, paste0(Sys.Date(), "_grunnlagsdata.xlsx"))
                write.csv(write.dat, file = csv_file)
                write.xlsx(write.dat, file = xlsx_file, overwrite = TRUE)
                cat("Base data exported\\n")
            '''
            
            with open(export_script, 'w') as f:
                f.write(export_code)
                
            print("Exporting base data...")
            subprocess.run([self.r_executable, str(export_script)], 
                         cwd=str(self.base_path), check=True)
            export_script.unlink()
            
            # Main analysis stages
            self.run_r_script("R-script/0_3_Calculated_Input_Values.R", "Calculating DEA input values")
            self.run_r_script("R-script/0_4_Company_Selection.R", "Company selection for special treatment")
            self.run_r_script("R-script/1_0_DEA.R", "Stage 1 - Data Envelopment Analysis")
            self.run_r_script("R-script/2_0_GeoCorrection.R", "Stage 2 - Geographic correction using OLS")
            self.run_r_script("R-script/3_0_Calibration.R", "Calibration on RAB including gf investments")
            self.run_r_script("R-script/Spec_OOTO-model.R", "Special models - OOTO companies")
            self.run_r_script("R-script/Spec_AvEff-model.R", "Special models - Average efficiency companies")
            self.run_r_script("R-script/4_0_Revenue_Cap_Calculation.R", "Revenue cap calculation")
            
            # Results and output
            self.run_r_script("R-script/Key_figures.R", "Key figures calculation")
            self.run_r_script("R-script/Print_results.R", "Results output generation")
            
            # Calculate execution time
            end_time = time.time()
            calc_time = end_time - self.start_time
            
            # Clean up temporary workspace file
            workspace_file = self.base_path / "temp_workspace.RData"
            if workspace_file.exists():
                workspace_file.unlink()
                print("✓ Cleaned up temporary workspace")
            
            print("="*60)
            print("✓ IRiR Analysis Pipeline Completed Successfully!")
            print(f"✓ Execution time: {calc_time:.2f} seconds")
            print(f"✓ Results saved to: {self.run_dir}")
            print("="*60)
            
            return {
                "status": "success",
                "execution_time": calc_time,
                "output_directory": str(self.run_dir),
                "timestamp": self.timestamp
            }
            
        except Exception as e:
            # Clean up temporary workspace file on error too
            workspace_file = self.base_path / "temp_workspace.RData"
            if workspace_file.exists():
                workspace_file.unlink()
            
            print("="*60)
            print(f"✗ Pipeline failed: {str(e)}")
            print("="*60)
            raise
    
    def run_scenario_analysis(self, scenarios):
        """Run multiple scenarios with different parameters"""
        print("Scenario analysis with subprocess mode not yet implemented.")
        print("Use the standard run_analysis_pipeline() for now.")
        return {"status": "not_implemented"}

def main():
    """Main execution function"""
    # Initialize orchestrator
    orchestrator = IRiROrchestrator()
    
    # Run standard analysis
    try:
        results = orchestrator.run_analysis_pipeline()
        print(f"Analysis completed successfully in {results['execution_time']:.2f} seconds")
        
    except Exception as e:
        print(f"Analysis failed: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    main()