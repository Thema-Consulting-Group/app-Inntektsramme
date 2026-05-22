/* ─────────────────────────────────────────────
   Inntektsramme – Alpine.js dashboard app
   ───────────────────────────────────────────── */

// ── Colour palette (Plotly) ─────────────────
const BRAND   = '#2563eb';
const BRAND_L = '#93c5fd';
const RED     = '#e63946';
const RED_L   = '#fca5a5';
const EMERALD = '#10b981';
const SLATE   = '#94a3b8';

// ── CSV column label mappings ────────────────
const CSV_COL_LABELS = {
  // identifiers
  id:                'ID',
  orgn:              'Organisasjonsnr',
  y:                 'År',
  comp:              'Selskap',
  // LD FHA outputs
  fha_ld_TOTXDEA:    'LD Total kostnad ekskl. nettap (1000 kr)',
  fha_ld_sub:        'LD Abonnenter',
  fha_ld_hv:         'LD Høyspentnett (km)',
  fha_ld_ss:         'LD Lavspentnett (km)',
  // RD FHA outputs
  fha_rd_TOTXDEA:    'RD Total kostnad ekskl. nettap (1000 kr)',
  'fha_rd_wv.ol':    'RD Vekt luftlinjer',
  'fha_rd_wv.uc':    'RD Vekt jordkabler',
  'fha_rd_wv.sc':    'RD Vekt sjøkabler',
  'fha_rd_wv.ss':    'RD Vekt lavspentnett',
  // LD grunnlagsdata
  ld_OPEXxS:         'LD OPEX ekskl. lønn (1000 kr)',
  ld_sal:            'LD Lønnskost (1000 kr)',
  'ld_sal.cap':      'LD Aktivert lønn (1000 kr)',
  ld_pens:           'LD Pensjonskost (1000 kr)',
  'ld_pens.eq':      'LD Pensjon egenkapital (1000 kr)',
  ld_impl:           'LD Pensjon impl. (1000 kr)',
  ld_391:            'LD §391 (1000 kr)',
  ld_elhub:          'LD Elhub (1000 kr)',
  ld_usla:           'LD Utestående saldo (1000 kr)',
  'ld_bv.sf':        'LD BV selvfinansiert (1000 kr)',
  'ld_dep.sf':       'LD AVS selvfinansiert (1000 kr)',
  'ld_bv.gf':        'LD BV gjennomfinansiert (1000 kr)',
  'ld_dep.gf':       'LD AVS gjennomfinansiert (1000 kr)',
  ld_cens:           'LD Nettleie (1000 kr)',
  ld_nl:             'LD Nettap (1000 kr)',
  ld_sub:            'LD Abonnenter',
  ld_hvoh:           'LD Høyspentnett luftlinjer (km)',
  ld_hvug:           'LD Høyspentnett jordkabler (km)',
  ld_hvsc:           'LD Høyspentnett sjøkabler (km)',
  ld_hv:             'LD Høyspentnett totalt (km)',
  ld_ss:             'LD Lavspentnett (km)',
  // RD grunnlagsdata
  rd_OPEXxS:         'RD OPEX ekskl. lønn (1000 kr)',
  rd_sal:            'RD Lønnskost (1000 kr)',
  'rd_sal.cap':      'RD Aktivert lønn (1000 kr)',
  rd_pens:           'RD Pensjonskost (1000 kr)',
  'rd_pens.eq':      'RD Pensjon egenkapital (1000 kr)',
  rd_impl:           'RD Pensjon impl. (1000 kr)',
  rd_391:            'RD §391 (1000 kr)',
  rd_elhub:          'RD Elhub (1000 kr)',
  rd_cga:            'RD CGA (1000 kr)',
  rd_cga_tidl:       'RD CGA tidligere år (1000 kr)',
  rd_coord:          'RD Koordineringskost (1000 kr)',
  rd_usla:           'RD Utestående saldo (1000 kr)',
  'rd_bv.sf':        'RD BV selvfinansiert (1000 kr)',
  'rd_dep.sf':       'RD AVS selvfinansiert (1000 kr)',
  'rd_bv.gf':        'RD BV gjennomfinansiert (1000 kr)',
  'rd_dep.gf':       'RD AVS gjennomfinansiert (1000 kr)',
  rd_cens:           'RD Nettleie (1000 kr)',
  rd_nl:             'RD Nettap (1000 kr)',
  'rd_wv.ol':        'RD Vekt luftlinjer',
  'rd_wv.uc':        'RD Vekt jordkabler',
  'rd_wv.sc':        'RD Vekt sjøkabler',
  'rd_wv.ss':        'RD Vekt lavspentnett',
  // totaler
  t_OPEXxS:         'Totalt OPEX ekskl. lønn (1000 kr)',
  t_sal:             'Totalt lønn (1000 kr)',
  t_cens:            'Totalt nettleie (1000 kr)',
  't_bv.sf':         'Totalt BV selvfinansiert (1000 kr)',
  't_dep.sf':        'Totalt AVS selvfinansiert (1000 kr)',
  // z-variabler
  ldz_salt:          'Z: Saltholdighet',
  ldz_coast_wind:    'Z: Kystv ind',
  ldz_water:         'Z: Vassdrag',
  ldz_incline:       'Z: Terrenghelning',
  ldz_prod:          'Z: Produksjon',
  ldz_snow_trees:    'Z: Snø/tre',
  ldz_forest_broadleaf: 'Z: Løvskog',
  ldz_snowdrift:     'Z: Snøfokk',
  ldz_snow_400:      'Z: Snø 400m',
  ldz_wind_99:       'Z: Vind 99-pst',
  ldz_frosthours:    'Z: Frosttimer',
  ldz_forest_mixed_conf: 'Z: Blandingsskog',
  ldz_mgc:           'Z: MGC',
  'ap.t_2':          'Avkastningsparameter t-2',
  'pnl.rc':          'PnL referansekost',
};

// ── Plotly base layout defaults ──────────────
const BASE_LAYOUT = {
  font:   { family: 'Inter, sans-serif', size: 12, color: '#475569' },
  paper_bgcolor: 'rgba(0,0,0,0)',
  plot_bgcolor:  'rgba(0,0,0,0)',
  margin: { t: 20, b: 40, l: 16, r: 16 },
  showlegend: true,
  legend: { orientation: 'h', yanchor: 'bottom', y: 1, xanchor: 'right', x: 1 },
};

const PLOTLY_CONFIG = { displayModeBar: false, responsive: true };

// ────────────────────────────────────────────
// Alpine.js app
// ────────────────────────────────────────────
function dashboard() {
  return {

    /* ── nav ─────────────────────────────── */
    tab: 'rme',
    navItems: [
      { id: 'rme',      label: 'RME Modell',            icon: '<svg viewBox="0 0 20 20" fill="currentColor"><path d="M2 11a1 1 0 011-1h2a1 1 0 011 1v5a1 1 0 01-1 1H3a1 1 0 01-1-1v-5zm6-4a1 1 0 011-1h2a1 1 0 011 1v9a1 1 0 01-1 1H9a1 1 0 01-1-1V7zm6-3a1 1 0 011-1h2a1 1 0 011 1v12a1 1 0 01-1 1h-2a1 1 0 01-1-1V4z"/></svg>' },
      { id: 'prognose', label: 'Prognosebygger',         icon: '<svg viewBox="0 0 20 20" fill="currentColor"><path fill-rule="evenodd" d="M3 3a1 1 0 000 2v8a2 2 0 002 2h2.586l-1.293 1.293a1 1 0 101.414 1.414L10 15.414l2.293 2.293a1 1 0 001.414-1.414L12.414 15H15a2 2 0 002-2V5a1 1 0 100-2H3zm11.707 4.707a1 1 0 00-1.414-1.414L10 9.586 8.707 8.293a1 1 0 00-1.414 0l-3 3a1 1 0 001.414 1.414L8 10.414l1.293 1.293a1 1 0 001.414 0l4-4z" clip-rule="evenodd"/></svg>' },
      { id: 'kostnader',label: 'Kostnader',              icon: '<svg viewBox="0 0 20 20" fill="currentColor"><path fill-rule="evenodd" d="M4 4a2 2 0 00-2 2v4a2 2 0 002 2V6h10a2 2 0 00-2-2H4zm2 6a2 2 0 012-2h8a2 2 0 012 2v4a2 2 0 01-2 2H8a2 2 0 01-2-2v-4zm6 4a2 2 0 100-4 2 2 0 000 4z" clip-rule="evenodd"/></svg>' },
      { id: 'frontier', label: 'Frontselskapsanalyse',   icon: '<svg viewBox="0 0 20 20" fill="currentColor"><path d="M9.049 2.927c.3-.921 1.603-.921 1.902 0l1.07 3.292a1 1 0 00.95.69h3.462c.969 0 1.371 1.24.588 1.81l-2.8 2.034a1 1 0 00-.364 1.118l1.07 3.292c.3.921-.755 1.688-1.54 1.118l-2.8-2.034a1 1 0 00-1.175 0l-2.8 2.034c-.784.57-1.838-.197-1.539-1.118l1.07-3.292a1 1 0 00-.364-1.118L2.98 8.72c-.783-.57-.38-1.81.588-1.81h3.461a1 1 0 00.951-.69l1.07-3.292z"/></svg>' },
      { id: 'elasticities', label: 'Oppgaveelastisiteter', icon: '<svg viewBox="0 0 20 20" fill="currentColor"><path fill-rule="evenodd" d="M11.3 1.046A1 1 0 0112 2v5h4a1 1 0 01.82 1.573l-7 10A1 1 0 018 18v-5H4a1 1 0 01-.82-1.573l7-10a1 1 0 011.12-.38z" clip-rule="evenodd"/></svg>' },
    ],

    /* ── global state ────────────────────── */
    loading:      false,
    globalError:  '',
    toast:        { msg: '', type: 'success' },
    latestRun:    '',
    selectedRun:  '',   // '' = always use latest
    availableRuns: [],  // [{name, complete}] populated from /api/runs

    /* ── Tab 1: RME ──────────────────────── */
    pipelineRunning: false,
    pipelineLogs:    [],
    irTable:         [],
    irColumns:       [],
    irMeta:          null,

    /* ── Grunnlagsdata upload ────────────── */
    grunnlag: { active: false, fileName: '', size: 0, uploading: false, dragOver: false },

    /* ── Tab 2: Prognose ─────────────────── */
    progCompanies: [],
    prog: {
      orgn: '', result: null, summary: [], years: [], allYears: [], compName: '',
      rho: 0.7, avs: 4.0,
      mergeYr: null, synergyPct: 0, oneOff: 0,
    },

    /* ── Tab 3: Kostnader ────────────────── */
    kost: { orgn: '', table: [] },
    kostColumns: [],

    /* ── CSV editor (RME tab) ────────────── */
    csvEdit: {
      loading:        false,
      saving:         false,
      file:           '',
      availableFiles: [],
      columns:        [],
      rows:           [],
      dirty:          false,
      runName:        '',
      focusCell:      '',
    },

    /* ── Tab 5: Task elasticities ──────────── */
    elas: {
      loading: false,
      estimated: null,   // raw response from /api/task-elasticities
      overrides: {},     // {key: value} user-edited values, e.g. {ld_hv_per_mnok: 0.12}
      useOverrides: false,
      scatterData: null, // raw obs from /api/task-elasticities/scatter
      scatterLoading: false,
      scatterVar: 'ld_hv',
      scatterOrgn: '',   // '' = all companies
    },

    /* ── Tab 4: Frontier ─────────────────── */
    deaCompanies: [],
    dea: {
      focusId:     '',
      excludeIds:  [],
      showExclude: false,
      showStage2:  false,
      showStage3:  false,
      dimX:        'ld_sub',
      dimY:        'ld_hv',
      normalize:   true,
      result:      null,
      focusRow:    null,
      focusPeers:  [],
      stableFront: [],
      droppedFront:[],
      newFront:    [],
      peersR:      {},
      peersLP:     [],
    },

    // ─────────────────────────────────────────
    get currentTabLabel() {
      return this.navItems.find(n => n.id === this.tab)?.label ?? '';
    },

    // ─────────────────────────────────────────
    async init() {
      await this.fetchLatestRun();
      await this.loadDeaCompanies();
      await this.loadProgCompanies();
      await this.initGrunnlagsStatus();
    },

    // ─── Helpers ─────────────────────────────

    showToast(msg, type = 'success') {
      this.toast = { msg, type };
      setTimeout(() => { this.toast.msg = ''; }, 4000);
    },

    async api(method, path, body) {
      const opts = { method, headers: { 'Content-Type': 'application/json' } };
      if (body !== undefined) opts.body = JSON.stringify(body);
      const res = await fetch(path, opts);
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: res.statusText }));
        throw new Error(err.detail ?? res.statusText);
      }
      return res.json();
    },

    // ─── Runs ────────────────────────────────

    async fetchLatestRun() {
      try {
        const data = await this.api('GET', '/api/runs');
        this.availableRuns = (data.runs ?? []);
        this.latestRun = this.availableRuns[0]?.name ?? '';
      } catch (_) {}
    },

    // Returns '?run_name=Run_...' if a specific run is selected, else ''
    _runQs() {
      return this.selectedRun ? `?run_name=${encodeURIComponent(this.selectedRun)}` : '';
    },

    // Returns run_name value for POST bodies
    _runName() {
      return this.selectedRun || null;
    },

    // Active run label for UI (selected or latest)
    get activeRunLabel() {
      return this.selectedRun || this.latestRun || 'Ingen';
    },

    // ─── Grunnlagsdata upload ─────────────────

    async initGrunnlagsStatus() {
      try {
        const d = await this.api('GET', '/api/upload-grunnlagsdata/status');
        this.grunnlag = { ...this.grunnlag, active: d.active, fileName: d.filename || '', size: d.size || 0 };
      } catch (_) {}
    },

    async uploadGrunnlagsdata(event) {
      const file = event.dataTransfer?.files?.[0] || event.target?.files?.[0];
      if (!file) return;
      this.grunnlag.dragOver = false;
      this.grunnlag.uploading = true;
      const form = new FormData();
      form.append('file', file);
      try {
        const res = await fetch('/api/upload-grunnlagsdata', { method: 'POST', body: form });
        if (!res.ok) {
          const err = await res.json().catch(() => ({ detail: res.statusText }));
          this.globalError = err.detail ?? 'Opplasting feilet';
          return;
        }
        const d = await res.json();
        this.grunnlag = { active: true, fileName: file.name, size: file.size, uploading: false, dragOver: false };
        this.showToast(`Grunnlagsdata lastet opp: ${file.name}`);
      } catch (e) {
        this.globalError = e.message;
      } finally {
        this.grunnlag.uploading = false;
      }
    },

    async clearGrunnlagsdata() {
      await fetch('/api/upload-grunnlagsdata', { method: 'DELETE' });
      this.grunnlag = { active: false, fileName: '', size: 0, uploading: false, dragOver: false };
      this.showToast('Grunnlagsdata fjernet – bruker siste R-kjøring');
    },

    // ─── Tab 1 ───────────────────────────────

    async runPipeline() {
      this.pipelineRunning = true;
      this.pipelineLogs = ['Starter R-pipeline …'];
      this.globalError = '';

      try {
        const es = new EventSource('/api/run-pipeline');
        es.onmessage = async (e) => {
          const msg = JSON.parse(e.data);
          if (msg.line)  this.pipelineLogs.push(msg.line);
          if (msg.error) { this.globalError = msg.error; es.close(); this.pipelineRunning = false; }
          if (msg.done) {
            es.close();
            this.pipelineRunning = false;
            if (msg.code === 0) {
              this.showToast('R-pipeline fullført!');
              await this.fetchLatestRun();
              this.selectedRun = this.latestRun; // auto-select the new run
              await this.loadIrTable();
              await this.loadDeaCompanies();
              await this.loadProgCompanies();
            } else {
              this.globalError = `Pipeline feilet (exit ${msg.code})`;
            }
          }
        };
        es.onerror = () => {
          this.pipelineRunning = false;
          this.globalError = 'Tilkobling til server brutt.';
          es.close();
        };
      } catch (e) {
        this.pipelineRunning = false;
        this.globalError = e.message;
      }
    },

    async loadIrTable() {
      this.loading = true;
      this.globalError = '';
      try {
        const data = await this.api('GET', `/api/ir-table${this._runQs()}`);
        this.irMeta    = data.meta;
        this.irTable   = data.table ?? [];
        this.irColumns = this.irTable.length ? Object.keys(this.irTable[0]) : [];
        this.showToast('Inntektsramme oppdatert');
      } catch (e) {
        this.globalError = e.message;
      } finally {
        this.loading = false;
      }
    },

    // ─── Tab 2 ───────────────────────────────

    async loadProgCompanies() {
      try {
        // Reuse from ir-table if available, otherwise parse from DEA companies
        if (this.irTable.length) {
          const seen = new Set();
          this.progCompanies = this.irTable
            .filter(r => r['Org.nr'] && r['Selskap'])
            .map(r => ({ orgn: r['Org.nr'], name: r['Selskap'] }))
            .filter(r => { if (seen.has(r.orgn)) return false; seen.add(r.orgn); return true; })
            .sort((a, b) => a.name.localeCompare(b.name));
        } else {
          // Try loading ir table silently
          const data = await this.api('GET', `/api/ir-table${this._runQs()}`).catch(() => null);
          if (data?.table) {
            const seen = new Set();
            this.progCompanies = data.table
              .filter(r => r['Org.nr'] && r['Selskap'])
              .map(r => ({ orgn: r['Org.nr'], name: r['Selskap'] }))
              .filter(r => { if (seen.has(r.orgn)) return false; seen.add(r.orgn); return true; })
              .sort((a, b) => a.name.localeCompare(b.name));
          }
        }
      } catch (_) {}
    },

    async runPrognose() {
      if (!this.prog.orgn) return;
      this.loading = true;
      this.globalError = '';
      try {
        const body = {
          orgn: Number(this.prog.orgn),
          rho: this.prog.rho,
          avs_sats: this.prog.avs,
          merge_yr: this.prog.mergeYr || null,
          synergy_pct: this.prog.synergyPct,
          one_off: this.prog.oneOff,
          run_name: this._runName(),
          task_elas_override: (this.elas.useOverrides && this.elas.estimated)
            ? this._buildElasOverride()
            : null,
        };
        const data = await this.api('POST', '/api/prognose', body);
        this.prog.result    = data.forecast ?? [];
        this.prog.summary   = data.summary  ?? [];
        this.prog.years     = data.years ?? [];
        this.prog.allYears  = data.all_years ?? data.years ?? [];
        this.prog.compName  = data.company_name ?? '';
        this.$nextTick(() => this.renderPrognoseChart());
      } catch (e) {
        this.globalError = e.message;
      } finally {
        this.loading = false;
      }
    },

    // ── Elasticity helpers ──────────────────────────────────────
    async loadElasticities() {
      this.elas.loading = true;
      try {
        const data = await this.api('GET', '/api/task-elasticities' + this._runQs());
        this.elas.estimated = data;
        // Populate overrides with estimated values as starting point
        const fields = this._elasticityFields();
        for (const f of fields) {
          if (!(f.key in this.elas.overrides)) {
            this.elas.overrides[f.key] = f.value(data);
          }
        }
      } catch (e) {
        this.globalError = e.message;
      } finally {
        this.elas.loading = false;
      }
    },

    _elasticityFields() {
      const e = this.elas.estimated ?? {};
      const ld = e.ld ?? {};
      const rd = e.rd ?? {};
      return [
        { key: 'ld_hv_per_mnok',    label: 'LD Høyspentnett km / MNOK',       value: d => d.ld?.hv_per_mnok  ?? 0 },
        { key: 'ld_ss_per_mnok',     label: 'LD Nettstasjoner / MNOK',          value: d => d.ld?.ss_per_mnok  ?? 0 },
        { key: 'ld_sub_per_mnok',    label: 'LD Nettkunder / MNOK',             value: d => d.ld?.sub_per_mnok ?? 0 },
        { key: 'rd_wv_ol_per_mnok',  label: 'RD Vekt luftlinjer / MNOK',        value: d => d.rd?.wv_ol_per_mnok ?? 0 },
        { key: 'rd_wv_uc_per_mnok',  label: 'RD Vekt jordkabler / MNOK',        value: d => d.rd?.wv_uc_per_mnok ?? 0 },
        { key: 'rd_wv_sc_per_mnok',  label: 'RD Vekt sjøkabler / MNOK',         value: d => d.rd?.wv_sc_per_mnok ?? 0 },
        { key: 'rd_wv_ss_per_mnok',  label: 'RD Vekt stasjonsvariabel / MNOK',  value: d => d.rd?.wv_ss_per_mnok ?? 0 },
      ];
    },

    _buildElasOverride() {
      const o = this.elas.overrides;
      return {
        ld: {
          hv_per_mnok:  Number(o.ld_hv_per_mnok  ?? 0),
          ss_per_mnok:  Number(o.ld_ss_per_mnok   ?? 0),
          sub_per_mnok: Number(o.ld_sub_per_mnok  ?? 0),
        },
        rd: {
          wv_ol_per_mnok: Number(o.rd_wv_ol_per_mnok ?? 0),
          wv_uc_per_mnok: Number(o.rd_wv_uc_per_mnok ?? 0),
          wv_sc_per_mnok: Number(o.rd_wv_sc_per_mnok ?? 0),
          wv_ss_per_mnok: Number(o.rd_wv_ss_per_mnok ?? 0),
        },
      };
    },

    resetElasOverrides() {
      if (!this.elas.estimated) return;
      const fields = this._elasticityFields();
      for (const f of fields) {
        this.elas.overrides[f.key] = f.value(this.elas.estimated);
      }
    },

    async loadElasScatter() {
      this.elas.scatterLoading = true;
      try {
        const data = await this.api('GET', '/api/task-elasticities/scatter' + this._runQs());
        this.elas.scatterData = data;
        this.$nextTick(() => this.renderElasScatter());
      } catch (e) {
        this.globalError = e.message;
      } finally {
        this.elas.scatterLoading = false;
      }
    },

    renderElasScatter() {
      const el = document.getElementById('elas-scatter-chart');
      if (!el || !this.elas.scatterData || !this.elas.estimated) return;

      const v = this.elas.scatterVar;
      const varMap = {
        'ld_hv':    { net: 'ld', delta: 'delta_hv',  beta: 'hv_per_mnok',    label: 'LD Høyspentnett km' },
        'ld_ss':    { net: 'ld', delta: 'delta_ss',  beta: 'ss_per_mnok',    label: 'LD Nettstasjoner' },
        'ld_sub':   { net: 'ld', delta: 'delta_sub', beta: 'sub_per_mnok',   label: 'LD Nettkunder' },
        'rd_wv_ol': { net: 'rd', delta: 'delta_ol',  beta: 'wv_ol_per_mnok', label: 'RD Vekt luftlinjer' },
        'rd_wv_uc': { net: 'rd', delta: 'delta_uc',  beta: 'wv_uc_per_mnok', label: 'RD Vekt jordkabler' },
        'rd_wv_sc': { net: 'rd', delta: 'delta_sc',  beta: 'wv_sc_per_mnok', label: 'RD Vekt sjøkabler' },
        'rd_wv_ss': { net: 'rd', delta: 'delta_ss',  beta: 'wv_ss_per_mnok', label: 'RD Vekt stasjonsvariabel' },
      };
      const cfg = varMap[v];
      if (!cfg) return;

      const obsArr = cfg.net === 'ld' ? this.elas.scatterData.ld : this.elas.scatterData.rd;
      const betaVal = this.elas.estimated?.[cfg.net]?.[cfg.beta] ?? 0;

      let filtered = obsArr;
      if (this.elas.scatterOrgn) {
        filtered = obsArr.filter(r => String(r.orgn) === String(this.elas.scatterOrgn));
      }

      if (!filtered?.length) return;

      const x = filtered.map(r => r.inv_mnok);
      const y = filtered.map(r => r[cfg.delta] ?? 0);
      const labels = filtered.map(r => {
        const co = this.progCompanies.find(c => String(c.orgn) === String(r.orgn));
        return `${co?.name ?? 'Selskap ' + r.orgn}, ${r.year}`;
      });
      const xMax = Math.max(...x) * 1.05;

      // OLS no-intercept for current filter
      const sumX2 = x.reduce((a, v) => a + v * v, 0);
      const sumXY = x.reduce((a, v, i) => a + v * y[i], 0);
      const localBeta = sumX2 > 0 ? sumXY / sumX2 : betaVal;

      Plotly.react(el, [
        {
          x, y,
          text: labels,
          mode: 'markers',
          type: 'scatter',
          name: 'Observasjoner',
          marker: { color: BRAND, size: 7, opacity: 0.65 },
          hovertemplate: '%{text}<br>Inv: %{x:.1f} MNOK<br>Δ: %{y:.3f}<extra></extra>',
        },
        {
          x: [0, xMax], y: [0, localBeta * xMax],
          mode: 'lines',
          name: `β = ${localBeta.toFixed(5)}${this.elas.scatterOrgn ? '' : ' (pooled)'}`,
          line: { color: RED, dash: 'dash', width: 2 },
          hoverinfo: 'skip',
        },
      ], {
        ...BASE_LAYOUT,
        xaxis: { title: 'Investering (MNOK)', gridcolor: '#f1f5f9', zeroline: true },
        yaxis: { title: 'Δ ' + cfg.label, gridcolor: '#f1f5f9', zeroline: true },
        height: 380,
      }, PLOTLY_CONFIG);
    },

    renderPrognoseChart() {
      const el = document.getElementById('prognose-chart');
      if (!el || !this.prog.summary?.length) return;

      const yrs = this.prog.years;
      const palette = {
        'Kostnadsgrunnlag': { color: SLATE,   dash: 'dot',    width: 1.5 },
        'Kostnadsnorm':     { color: BRAND,   dash: 'dash',   width: 2   },
        'Inntektsramme':    { color: EMERALD, dash: 'solid',  width: 2.5 },
        'Driftsresultat':   { color: RED,     dash: 'solid',  width: 1.5 },
      };

      const kkkRows = this.prog.summary.filter(r =>
        ['Kostnadsgrunnlag', 'Kostnadsnorm', 'Inntektsramme', 'Driftsresultat'].includes(r['Parameter'])
      );

      const traces = kkkRows.map(row => {
        const p = row['Parameter'];
        const s = palette[p] || { color: BRAND, dash: 'solid', width: 2 };
        return {
          x: yrs,
          y: yrs.map(yr => row[yr] ?? null),
          mode: 'lines+markers',
          name: p,
          line: { color: s.color, dash: s.dash, width: s.width },
          marker: { size: 5, color: s.color },
          hovertemplate: '%{x}: %{y:,.0f} kkr<extra>' + p + '</extra>',
        };
      });

      if (!traces.length) return;

      Plotly.react(el, traces, {
        ...BASE_LAYOUT,
        margin: { t: 50, b: 40, l: 60, r: 16 },
        yaxis: { title: '1000 NOK', gridcolor: '#f1f5f9', rangemode: 'tozero' },
        xaxis: { title: 'År', dtick: 1, gridcolor: '#f1f5f9' },
        height: 300,
      }, PLOTLY_CONFIG);

      // Render efficiency chart
      const effEl = document.getElementById('prognose-eff-chart');
      if (!effEl) return;
      const effRows = this.prog.summary.filter(r =>
        ['Effektivitet Dnett %', 'Effektivitet vektet %', 'Avkastning NVE %'].includes(r['Parameter'])
      );
      const effTraces = effRows.map(row => ({
        x: yrs,
        y: yrs.map(yr => row[yr] ?? null),
        mode: 'lines+markers',
        name: row['Parameter'],
        hovertemplate: '%{x}: %{y:.2f} %<extra>' + row['Parameter'] + '</extra>',
      }));
      Plotly.react(effEl, effTraces, {
        ...BASE_LAYOUT,
        margin: { t: 50, b: 40, l: 50, r: 16 },
        yaxis: { title: '%', gridcolor: '#f1f5f9', rangemode: 'tozero' },
        xaxis: { title: 'År', dtick: 1, gridcolor: '#f1f5f9' },
        height: 240,
      }, PLOTLY_CONFIG);
    },

    // ─── Tab 3 ───────────────────────────────

    // ── CSV editor ───────────────────────────
    async loadRunCsvFiles() {
      const run = this.selectedRun || '';
      const qs  = run ? `?run_name=${encodeURIComponent(run)}` : '';
      try {
        const data = await this.api('GET', `/api/run-csv/files${qs}`);
        this.csvEdit.availableFiles = data.files ?? [];
        // Auto-select first file if none chosen or previous choice gone
        const names = this.csvEdit.availableFiles.map(f => f.filename);
        if (!names.includes(this.csvEdit.file)) {
          this.csvEdit.file = names[0] ?? '';
        }
      } catch(e) { /* silent */ }
    },

    async loadRunCsv() {
      if (!this.csvEdit.file) return;
      this.csvEdit.loading = true;
      this.csvEdit.dirty   = false;
      const run = this.selectedRun || '';
      const qs  = `?filename=${encodeURIComponent(this.csvEdit.file)}` + (run ? `&run_name=${encodeURIComponent(run)}` : '');
      try {
        const data = await this.api('GET', `/api/run-csv${qs}`);
        this.csvEdit.columns = data.columns;
        this.csvEdit.rows    = data.rows;
        this.csvEdit.runName = data.run_dir;
      } catch(e) {
        this.globalError = e.message;
      } finally {
        this.csvEdit.loading = false;
      }
    },

    async saveRunCsv() {
      if (!this.csvEdit.runName) return;
      this.csvEdit.saving = true;
      const qs = `?filename=${encodeURIComponent(this.csvEdit.file)}&run_name=${encodeURIComponent(this.csvEdit.runName)}`;
      try {
        await this.api('PUT', `/api/run-csv${qs}`, { rows: this.csvEdit.rows });
        this.csvEdit.dirty = false;
        this.showToast('CSV lagret ✓');
      } catch(e) {
        this.globalError = e.message;
      } finally {
        this.csvEdit.saving = false;
      }
    },

    csvColLabel(col) {
      return CSV_COL_LABELS[col] ?? col;
    },

    csvCompanyName(id) {
      const all = [...(this.progCompanies || []), ...(this.deaCompanies || [])];
      const match = all.find(c => String(c.id) === String(id));
      return match ? match.name : null;
    },

    async loadKostnader() {
      this.loading = true;
      this.globalError = '';
      try {
        let path = `/api/kostnader${this._runQs()}`;
        if (this.kost.orgn) path += (this._runQs() ? '&' : '?') + `orgn=${this.kost.orgn}`;
        const data = await this.api('GET', path);
        this.kost.table  = data.table ?? [];
        this.kostColumns = this.kost.table.length ? Object.keys(this.kost.table[0]) : [];
      } catch (e) {
        this.globalError = e.message;
      } finally {
        this.loading = false;
      }
    },

    // ─── Tab 4 ───────────────────────────────

    async loadDeaCompanies() {
      try {
        const data = await this.api('GET', `/api/ld-dea${this._runQs()}`);
        this.deaCompanies = (data.companies ?? []).sort((a, b) =>
          (a.comp || '').localeCompare(b.comp || '')
        );
        // Default focus to NETTSELSKAPET AS
        const ns = this.deaCompanies.find(c => c.comp?.includes('NETTSELSKAPET'));
        if (ns) this.dea.focusId = ns.id;
      } catch (_) {}
    },

    async runScenario() {
      if (!this.dea.focusId) return;
      this.loading = true;
      this.globalError = '';
      this.dea.result = null;
      this.dea.showExclude = false;

      try {
        const data = await this.api('POST', '/api/frontier-scenario', {
          focus_id: Number(this.dea.focusId),
          exclude_ids: this.dea.excludeIds.map(Number),
          run_name: this._runName(),
        });

        this.dea.result = data.scenario ?? [];

        // Focus row
        this.dea.focusRow = this.dea.result.find(r => r.id === Number(this.dea.focusId)) ?? null;

        // Peers
        this.dea.peersR  = data.focus_peers_r ?? {};
        this.dea.peersLP = data.focus_peers_lp ?? [];

        // Focus company peers for display
        const hasExcl = this.dea.excludeIds.length > 0;
        if (hasExcl && this.dea.peersLP.length) {
          const total = this.dea.peersLP.reduce((s, p) => s + p.lambda, 0);
          this.dea.focusPeers = this.dea.peersLP.map(p => ({
            comp: p.comp, share: total > 0 ? p.lambda / total : 0,
          }));
        } else {
          const r = this.dea.peersR;
          const total = Object.values(r).reduce((s, v) => s + v, 0);
          this.dea.focusPeers = Object.entries(r).map(([comp, lambda]) => ({
            comp, share: total > 0 ? lambda / total : 0,
          }));
        }

        // Frontier composition
        const baseIds = new Set((data.frontier_base  ?? []).map(c => c.id));
        const scenIds = new Set((data.frontier_scenario ?? []).map(c => c.id));
        const allIds  = new Set([...baseIds, ...scenIds]);
        const idToName = {};
        [...(data.frontier_base ?? []), ...(data.frontier_scenario ?? [])].forEach(c => { idToName[c.id] = c.name; });
        const nameOf = id => ({ id, name: idToName[id] ?? String(id) });

        this.dea.stableFront  = [...allIds].filter(id => baseIds.has(id) && scenIds.has(id)).map(nameOf);
        this.dea.droppedFront = [...allIds].filter(id => baseIds.has(id) && !scenIds.has(id)).map(nameOf);
        this.dea.newFront     = [...allIds].filter(id => !baseIds.has(id) && scenIds.has(id)).map(nameOf);

        this.$nextTick(() => {
          this.renderPeerChart();
          this.renderEffChart();
          this.renderScatterChart();
        });
      } catch (e) {
        this.globalError = e.message;
      } finally {
        this.loading = false;
      }
    },

    renderPeerChart() {
      const el = document.getElementById('peer-chart');
      if (!el) return;

      // Use LP peers if scenario active, else R peers
      let labels, values;
      const hasExclusion = this.dea.excludeIds.length > 0;
      if (hasExclusion && this.dea.peersLP.length) {
        labels = this.dea.peersLP.map(p => p.comp);
        values = this.dea.peersLP.map(p => p.lambda);
      } else {
        const r = this.dea.peersR;
        labels = Object.keys(r);
        values = Object.values(r);
      }

      if (!labels.length) {
        Plotly.purge(el);
        return;
      }

      Plotly.react(el, [{
        type: 'pie',
        labels, values,
        hole: 0.45,
        textinfo: 'label+percent',
        hovertemplate: '%{label}: %{value:.3f}<extra></extra>',
        marker: { colors: [BRAND, '#60a5fa', '#93c5fd', '#bfdbfe', EMERALD, '#6ee7b7', RED, '#fca5a5'] },
      }], {
        ...BASE_LAYOUT,
        margin: { t: 10, b: 10, l: 10, r: 10 },
        height: 240,
        showlegend: false,
      }, PLOTLY_CONFIG);
    },

    renderEffChart() {
      const el = document.getElementById('eff-chart');
      if (!el || !this.dea.result?.length) return;

      const sorted = [...this.dea.result].sort((a, b) => a.eff_s1_baseline - b.eff_s1_baseline);
      const labels   = sorted.map(r => r.comp || String(r.id));
      const focusId  = Number(this.dea.focusId);
      const isFocus  = sorted.map(r => r.id === focusId);
      const baseColors = isFocus.map(f => f ? RED   : BRAND);
      const scenColors = isFocus.map(f => f ? RED_L : BRAND_L);
      const s2Color    = isFocus.map(f => f ? '#f97316' : '#6ee7b7');  // orange / emerald

      const s2 = this.dea.showStage2;
      const hasExcl = this.dea.excludeIds.length > 0;

      const traces = [
        {
          type: 'bar', orientation: 'h',
          name: s2 ? 'Trinn 1 (nåsit.)' : 'Nåsituasjon',
          x: sorted.map(r => r.eff_s1_baseline),
          y: labels,
          marker: { color: baseColors },
          hovertemplate: '%{y}: %{x:.3f}<extra>Trinn 1 nåsit.</extra>',
        },
      ];

      if (hasExcl) {
        traces.push({
          type: 'bar', orientation: 'h',
          name: s2 ? 'Trinn 1 (scenario)' : 'Etter fusjon',
          x: sorted.map(r => r.eff_s1_scenario),
          y: labels,
          marker: { color: scenColors },
          hovertemplate: '%{y}: %{x:.3f}<extra>Trinn 1 scenario</extra>',
        });
      }

      if (s2) {
        traces.push({
          type: 'scatter', mode: 'markers', orientation: 'h',
          name: 'Trinn 2 geo-korrigert (nåsit.)',
          x: sorted.map(r => r.eff_s2_approx_base),
          y: labels,
          marker: { color: s2Color, symbol: 'diamond', size: 7, line: { width: 1, color: '#fff' } },
          hovertemplate: '%{y}: %{x:.3f}<extra>Trinn 2 nåsit.</extra>',
        });
        if (hasExcl) {
          traces.push({
            type: 'scatter', mode: 'markers', orientation: 'h',
            name: 'Trinn 2 geo-korrigert (scenario)',
            x: sorted.map(r => r.eff_s2_approx_scenario),
            y: labels,
            marker: { color: '#fb923c', symbol: 'circle', size: 7, line: { width: 1, color: '#fff' } },
            hovertemplate: '%{y}: %{x:.3f}<extra>Trinn 2 scenario</extra>',
          });
        }
      }

      const s3 = this.dea.showStage3;
      const s3Color = isFocus.map(f => f ? '#7c3aed' : '#a78bfa');  // violet
      if (s3) {
        traces.push({
          type: 'scatter', mode: 'markers', orientation: 'h',
          name: 'Trinn 3 kalibrert (nåsit.)',
          x: sorted.map(r => r.eff_s3_approx_base),
          y: labels,
          marker: { color: s3Color, symbol: 'star', size: 8, line: { width: 1, color: '#fff' } },
          hovertemplate: '%{y}: %{x:.3f}<extra>Trinn 3 nåsit.</extra>',
        });
        if (hasExcl) {
          traces.push({
            type: 'scatter', mode: 'markers', orientation: 'h',
            name: 'Trinn 3 kalibrert (scenario)',
            x: sorted.map(r => r.eff_s3_approx_scenario),
            y: labels,
            marker: { color: '#c4b5fd', symbol: 'star-open', size: 8, line: { width: 1.5, color: '#7c3aed' } },
            hovertemplate: '%{y}: %{x:.3f}<extra>Trinn 3 scenario</extra>',
          });
        }
      }

      const chartHeight = Math.max(400, sorted.length * 18);
      el.style.height = chartHeight + 'px';

      Plotly.react(el, traces, {
        ...BASE_LAYOUT,
        barmode: 'overlay',
        height: chartHeight,
        margin: { t: 20, b: 40, l: 8, r: 16 },
        xaxis: { title: 'Effektivitet', range: [0, 1.3], gridcolor: '#f1f5f9' },
        yaxis: { title: null, automargin: true },
        shapes: [
          { type: 'line', x0: 1, x1: 1, y0: 0, y1: 1, yref: 'paper',
            line: { color: EMERALD, dash: 'dash', width: 1.5 } },
        ],
        annotations: [{ x: 1.01, y: 1, xref: 'x', yref: 'paper', text: 'Front',
                        showarrow: false, font: { color: EMERALD, size: 11 } }],
      }, PLOTLY_CONFIG);
    },

    renderScatterChart() {
      const el = document.getElementById('scatter-chart');
      if (!el || !this.dea.result?.length) return;

      const dimX = this.dea.dimX;
      const dimY = this.dea.dimY;
      const norm = this.dea.normalize;
      const data = this.dea.result;
      const focusId = Number(this.dea.focusId);
      const frontierIds = new Set((this.dea.stableFront || []).map(c => c.id));

      const val = (r, dim) => norm ? (r[dim] / r.X_cb * 1000) : r[dim];
      const fmtTip = norm
        ? (dim) => `${dim}/kostn.: %{x:.3f}`
        : (dim) => `${dim}: %{x:.0f}`;
      const xLabel = norm ? `${dimX} per MNOK kostnader` : dimX;
      const yLabel = norm ? `${dimY} per MNOK kostnader` : dimY;

      const tipX = norm ? (dimX + ' / MNOK: %{x:.4f}') : (dimX + ': %{x:.0f}');
      const tipY = norm ? (dimY + ' / MNOK: %{y:.4f}') : (dimY + ': %{y:.0f}');
      const tip     = `<b>%{text}</b><br>${tipX}<br>${tipY}<extra></extra>`;
      const tipWithEff = `<b>%{text}</b><br>${tipX}<br>${tipY}<br>Eff S1: %{customdata:.3f}<extra></extra>`;

      // All non-focus companies (frontier + others combined, colored by efficiency)
      const nonFocus    = data.filter(r => r.id !== focusId);
      const focusRows   = data.filter(r => r.id === focusId);
      const frontierRows = data.filter(r => r.id !== focusId && frontierIds.has(r.id));

      const effValues = nonFocus.map(r => r.eff_s1_baseline ?? 0);
      const isFront   = nonFocus.map(r => frontierIds.has(r.id));

      // ── 2D frontier: upper convex hull of ALL companies ──────────────────
      // CRS DEA frontier in normalized output space must be convex — any line
      // segment between two frontier points lies inside (below) the frontier.
      // Upper convex hull enforces this: no concave "dips" allowed.
      const allPts = data.map(r => ({ x: val(r, dimX), y: val(r, dimY) }));
      const sortedHull = [...allPts].sort((a, b) => a.x !== b.x ? a.x - b.x : b.y - a.y);
      const hull = [];
      for (const p of sortedHull) {
        while (hull.length >= 2) {
          const a = hull[hull.length - 2], b = hull[hull.length - 1];
          // cross >= 0 → b is below (or on) line a→p → not on upper hull → remove
          const cross = (b.x - a.x) * (p.y - a.y) - (b.y - a.y) * (p.x - a.x);
          if (cross >= 0) hull.pop();
          else break;
        }
        hull.push(p);
      }
      // Trim to the descending section (peak-y point → max-x point)
      const peakIdx = hull.reduce((mi, p, i) => p.y > hull[mi].y ? i : mi, 0);
      const frontHull = hull.slice(peakIdx);
      // Axis caps so the envelope visually reaches the axes
      const frontLineX = [frontHull[0].x, ...frontHull.map(p => p.x), frontHull.at(-1).x];
      const frontLineY = [Math.max(...allPts.map(p => p.y)) * 1.04,
                          ...frontHull.map(p => p.y), 0];
      // ─────────────────────────────────────────────────────────────────────

      const effFocusVal = focusRows[0]?.eff_s1_baseline ?? 0;
      const effColorScale = [[0, '#fca5a5'], [0.4, '#93c5fd'], [0.85, '#6ee7b7'], [1.0, '#059669']];

      const traces = [
        // 2D convex hull frontier
        {
          type: 'scatter', mode: 'lines',
          name: '2D konveks hull-front',
          x: frontLineX,
          y: frontLineY,
          line: { color: '#475569', dash: 'dot', width: 1.5 },
          hoverinfo: 'skip',
          showlegend: true,
        },
        // All non-focus companies — color = efficiency score, shape = 3D-frontier vs not
        {
          type: 'scatter', mode: 'markers',
          name: 'Selskaper (farge = eff. trinn 1)',
          x: nonFocus.map(r => val(r, dimX)),
          y: nonFocus.map(r => val(r, dimY)),
          text: nonFocus.map(r => r.comp || r.id),
          customdata: effValues,
          marker: {
            color: effValues,
            colorscale: effColorScale,
            cmin: 0.7, cmax: 1.0,
            size: isFront.map(f => f ? 11 : 7),
            symbol: isFront.map(f => f ? 'diamond' : 'circle'),
            line: { color: isFront.map(f => f ? '#1e293b' : 'rgba(0,0,0,0)'), width: 1.5 },
            colorbar: {
              title: { text: 'Eff. trinn 1', side: 'right' },
              thickness: 12, len: 0.6,
              tickformat: '.0%',
            },
          },
          hovertemplate: tipWithEff,
        },
      ];

      // Focus company — large diamond, colored by efficiency (same scale), thick border
      if (focusRows.length) {
        const fr = focusRows[0];
        traces.push({
          type: 'scatter', mode: 'markers+text',
          name: (fr.comp || fr.id) + ' (fokus)',
          x: [val(fr, dimX)],
          y: [val(fr, dimY)],
          text: [fr.comp || fr.id],
          customdata: [fr.eff_s1_baseline ?? 0],
          textposition: 'top center',
          textfont: { size: 10, color: '#1e293b' },
          marker: {
            color: [fr.eff_s1_baseline ?? 0],
            colorscale: effColorScale,
            cmin: 0.7, cmax: 1.0,
            size: 16,
            symbol: 'diamond',
            line: { color: '#1e293b', width: 2.5 },
            showscale: false,
          },
          hovertemplate: tipWithEff,
        });
      }

      Plotly.react(el, traces, {
        ...BASE_LAYOUT,
        height: 420,
        xaxis: { title: xLabel, gridcolor: '#f1f5f9', rangemode: 'tozero' },
        yaxis: { title: yLabel, gridcolor: '#f1f5f9', rangemode: 'tozero' },
      }, PLOTLY_CONFIG);
    },

    // ─── Sort / format ────────────────────────

    sortTable(tableKey, col) {
      const tbl = this[tableKey];
      if (!Array.isArray(tbl) || !tbl.length) return;
      const asc = this._sortState?.[col] !== 'asc';
      if (!this._sortState) this._sortState = {};
      this._sortState[col] = asc ? 'asc' : 'desc';
      this[tableKey] = [...tbl].sort((a, b) => {
        const av = a[col], bv = b[col];
        if (av == null) return 1; if (bv == null) return -1;
        if (typeof av === 'number') return asc ? av - bv : bv - av;
        return asc ? String(av).localeCompare(String(bv)) : String(bv).localeCompare(String(av));
      });
    },

    fmt(v) {
      if (v == null) return '—';
      if (typeof v === 'number') return v.toLocaleString('no-NO', { maximumFractionDigits: 0 });
      return String(v);
    },

    fmtCell(v) {
      if (v == null || v === '') return '—';
      if (typeof v === 'number') {
        if (Number.isInteger(v)) return v.toLocaleString('no-NO');
        return v.toLocaleString('no-NO', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
      }
      return String(v);
    },

    pct(v) {
      if (v == null) return '—';
      return (v * 100).toFixed(2) + ' %';
    },

    fmtMnok(v) {
      if (v == null) return '—';
      return v.toFixed(2) + ' MNOK';
    },

    fmtKkr(v) {
      if (v == null || v === undefined) return '—';
      const mnok = v / 1000;
      return mnok.toLocaleString('nb-NO', { maximumFractionDigits: 1 }) + ' MNOK';
    },

    downloadCsv(rows, name) {
      if (!rows?.length) return;
      const cols = Object.keys(rows[0]);
      const csv  = [cols.join(';'), ...rows.map(r => cols.map(c => {
        const v = r[c]; if (v == null) return '';
        const s = String(v);
        return s.includes(';') || s.includes('"') ? `"${s.replace(/"/g,'""')}"` : s;
      }).join(';'))].join('\r\n');
      const blob = new Blob(['\uFEFF' + csv], { type: 'text/csv;charset=utf-8;' });
      const url  = URL.createObjectURL(blob);
      const a    = Object.assign(document.createElement('a'), { href: url, download: `${name}.csv` });
      a.click(); URL.revokeObjectURL(url);
    },
  };
}
