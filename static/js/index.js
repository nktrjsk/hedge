window.app = Vue.createApp({
  el: '#vue',
  mixins: [windowMixin],
  delimiters: ['${', '}'],

  data: function () {
    return {
      config: null,
      status: null,
      walletStatuses: [],
      events: [],
      selectedWalletIds: [],
      showSecrets: false,

      configDialog: false,
      walletsDialog: false,

      statusLoading: false,
      eventsLoading: false,
      configSaving: false,
      walletsSaving: false,
      syncLoading: false,

      configForm: {
        lnm_key: '',
        lnm_secret: '',
        lnm_passphrase: '',
        leverage: 2,
        testnet: false
      },

      eventsColumns: [
        {
          name: 'created_at', label: 'Čas', field: 'created_at', align: 'left', sortable: true,
          format: function (val) { return new Date(val).toLocaleString('cs-CZ') }
        },
        {name: 'event_type', label: 'Typ', field: 'event_type', align: 'left'},
        {name: 'wallet_id', label: 'Wallet', field: 'wallet_id', align: 'left',
          format: function (val) { return val ? val.substring(0, 8) + '...' : '-' }},
        {name: 'sats_delta', label: 'Sats \u0394', field: 'sats_delta', align: 'right'},
        {
          name: 'usd_price', label: 'BTC/USD', field: 'usd_price', align: 'right',
          format: function (val) { return val > 0 ? '$' + Math.round(val).toLocaleString('cs-CZ') : '-' }
        },
        {name: 'usd_notional_delta', label: 'USD \u0394', field: 'usd_notional_delta', align: 'right'},
        {name: 'status', label: 'Stav', field: 'status', align: 'center'},
        {name: 'error_msg', label: '', field: 'error_msg', align: 'center'}
      ],

      _statusInterval: null
    }
  },

  computed: {
    driftClass: function () {
      if (!this.status) return ''
      var d = Math.abs(this.status.drift_pct)
      if (d < 2) return ''
      if (d < 5) return 'bg-warning text-white'
      return 'bg-negative text-white'
    },

    activeWallet: function () {
      return this.g.user.wallets.length > 0 ? this.g.user.wallets[0] : null
    }
  },

  mounted: function () {
    this.loadConfig()
    this.loadEvents()
    var self = this
    this._statusInterval = setInterval(function () {
      if (self.config) {
        self.loadStatus()
        self.loadWalletStatuses()
      }
    }, 30000)
  },

  beforeUnmount: function () {
    if (this._statusInterval) clearInterval(this._statusInterval)
  },

  methods: {
    adminKey: function () {
      return this.activeWallet ? this.activeWallet.adminkey : null
    },

    inKey: function () {
      return this.activeWallet ? this.activeWallet.inkey : null
    },

    openConfigDialog: function () {
      if (this.config) {
        this.configForm.leverage = this.config.leverage
        this.configForm.testnet = this.config.testnet
      }
      this.configForm.lnm_key = ''
      this.configForm.lnm_secret = ''
      this.configForm.lnm_passphrase = ''
      this.configDialog = true
    },

    openWalletsDialog: function () {
      this.walletsDialog = true
    },

    loadConfig: async function () {
      var key = this.adminKey()
      if (!key) return
      try {
        var resp = await LNbits.api.request('GET', '/hedge/api/v1/config', key)
        this.config = resp.data
        if (this.config) {
          await this.loadStatus()
          await this.loadHedgedWallets()
          await this.loadWalletStatuses()
        } else {
          this.configDialog = true
        }
      } catch (err) {
        if (err.response && err.response.status === 404) {
          this.config = null
          this.configDialog = true
        } else {
          LNbits.utils.notifyApiError(err)
        }
      }
    },

    loadStatus: async function () {
      var key = this.inKey()
      if (!key || !this.config) return
      this.statusLoading = true
      try {
        var resp = await LNbits.api.request('GET', '/hedge/api/v1/status', key)
        this.status = resp.data
      } catch (err) {
        if (!err.response || err.response.status !== 404) {
          LNbits.utils.notifyApiError(err)
        }
      } finally {
        this.statusLoading = false
      }
    },

    loadHedgedWallets: async function () {
      var key = this.adminKey()
      if (!key) return
      try {
        var resp = await LNbits.api.request('GET', '/hedge/api/v1/wallets', key)
        this.selectedWalletIds = resp.data
      } catch (err) {
        LNbits.utils.notifyApiError(err)
      }
    },

    loadWalletStatuses: async function () {
      var key = this.inKey()
      if (!key || !this.config) return
      try {
        var resp = await LNbits.api.request('GET', '/hedge/api/v1/wallet-statuses', key)
        this.walletStatuses = resp.data
      } catch (err) {
        // tiše ignorujeme
      }
    },

    loadEvents: async function () {
      var key = this.inKey()
      if (!key) return
      this.eventsLoading = true
      try {
        var resp = await LNbits.api.request('GET', '/hedge/api/v1/events', key)
        this.events = resp.data
      } catch (err) {
        if (!err.response || err.response.status !== 404) {
          LNbits.utils.notifyApiError(err)
        }
      } finally {
        this.eventsLoading = false
      }
    },

    saveConfig: async function () {
      var key = this.adminKey()
      if (!key) return
      this.configSaving = true
      try {
        await LNbits.api.request('POST', '/hedge/api/v1/config', key, this.configForm)
        this.$q.notify({type: 'positive', message: 'Nastavení uloženo a API klíče ověřeny'})
        this.configDialog = false
        this.configForm.lnm_key = ''
        this.configForm.lnm_secret = ''
        this.configForm.lnm_passphrase = ''
        await this.loadConfig()
      } catch (err) {
        LNbits.utils.notifyApiError(err)
      } finally {
        this.configSaving = false
      }
    },

    saveWallets: async function () {
      var key = this.adminKey()
      if (!key) return
      this.walletsSaving = true
      try {
        await LNbits.api.request('PUT', '/hedge/api/v1/wallets', key, this.selectedWalletIds)
        this.$q.notify({type: 'positive', message: 'Peněženky uloženy'})
        this.walletsDialog = false
        await this.loadWalletStatuses()
        await this.loadStatus()
      } catch (err) {
        LNbits.utils.notifyApiError(err)
      } finally {
        this.walletsSaving = false
      }
    },

    manualSync: async function () {
      var key = this.adminKey()
      if (!key) return
      this.syncLoading = true
      try {
        await LNbits.api.request('POST', '/hedge/api/v1/sync', key)
        this.$q.notify({type: 'info', message: 'Synchronizace spuštěna'})
        var self = this
        setTimeout(function () {
          self.loadStatus()
          self.loadEvents()
        }, 2000)
      } catch (err) {
        LNbits.utils.notifyApiError(err)
      } finally {
        this.syncLoading = false
      }
    },

    exportEvents: function () {
      LNbits.utils.exportCSV(this.eventsColumns, this.events, 'hedge-events')
    },

    formatUsd: function (val) {
      if (val === null || val === undefined) return '-'
      return '$' + Math.abs(val).toLocaleString('cs-CZ', {minimumFractionDigits: 2, maximumFractionDigits: 2})
    },

    formatSats: function (val) {
      if (val === null || val === undefined) return '-'
      return Math.abs(val).toLocaleString('cs-CZ')
    },

    formatTime: function (val) {
      if (!val) return '-'
      return new Date(val).toLocaleString('cs-CZ')
    },

    statusColor: function (s) {
      return {success: 'positive', failed: 'negative', pending: 'warning', skipped: 'grey'}[s] || 'grey'
    },

    eventIcon: function (t) {
      return {payment_received: 'arrow_downward', payment_sent: 'arrow_upward', reconciliation: 'sync', error: 'error'}[t] || 'radio_button_unchecked'
    },

    eventLabel: function (t) {
      return {payment_received: 'Přijato', payment_sent: 'Odesláno', reconciliation: 'Reconciliation', error: 'Chyba'}[t] || t
    }
  }
})
