window.app = Vue.createApp({
  el: '#vue',
  mixins: [windowMixin],
  delimiters: ['${', '}'],
  data: function () {
    return {
      invoiceAmount: 10,
      qrValue: '',
      myex: [],
      myexTable: {
        columns: [
          {name: 'id', align: 'left', label: 'ID', field: 'id'},
          {name: 'name', align: 'left', label: 'Name', field: 'name'},
          {
            name: 'wallet',
            align: 'left',
            label: 'Wallet',
            field: 'wallet'
          },
          {
            name: 'total',
            align: 'left',
            label: 'Total sent/received',
            field: 'total'
          }
        ],
        pagination: {
          rowsPerPage: 10
        }
      },
      formDialog: {
        show: false,
        data: {},
        advanced: {}
      },
      urlDialog: {
        show: false,
        data: {}
      }
    }
  },

  ///////////////////////////////////////////////////
  ////////////////METHODS FUNCTIONS//////////////////
  ///////////////////////////////////////////////////

  methods: {
    async closeFormDialog() {
      this.formDialog.show = false
      this.formDialog.data = {}
    },
    async getHedges() {
      await LNbits.api
        .request(
          'GET',
          '/hedge/api/v1/myex',
          this.g.user.wallets[0].inkey
        )
        .then(response => {
          this.myex = response.data
        })
        .catch(err => {
          LNbits.utils.notifyApiError(err)
        })
    },
    async sendHedgeData() {
      const data = {
        name: this.formDialog.data.name,
        lnurlwithdrawamount: this.formDialog.data.lnurlwithdrawamount,
        lnurlpayamount: this.formDialog.data.lnurlpayamount
      }
      const wallet = _.findWhere(this.g.user.wallets, {
        id: this.formDialog.data.wallet
      })
      if (this.formDialog.data.id) {
        data.id = this.formDialog.data.id
        data.total = this.formDialog.data.total
        await this.updateHedge(wallet, data)
      } else {
        await this.createHedge(wallet, data)
      }
    },

    async updateHedgeForm(tempId) {
      const hedge = _.findWhere(this.myex, {id: tempId})
      this.formDialog.data = {
        ...hedge
      }
      if (this.formDialog.data.tip_wallet != '') {
        this.formDialog.advanced.tips = true
      }
      if (this.formDialog.data.withdrawlimit >= 1) {
        this.formDialog.advanced.otc = true
      }
      this.formDialog.show = true
    },
    async createHedge(wallet, data) {
      data.wallet = wallet.id
      await LNbits.api
        .request('POST', '/hedge/api/v1/myex', wallet.adminkey, data)
        .then(response => {
          this.myex.push(response.data)
          this.closeFormDialog()
        })
        .catch(error => {
          LNbits.utils.notifyApiError(error)
        })
    },

    async updateHedge(wallet, data) {
      data.wallet = wallet.id
      await LNbits.api
        .request(
          'PUT',
          `/hedge/api/v1/myex/${data.id}`,
          wallet.adminkey,
          data
        )
        .then(response => {
          this.myex = _.reject(this.myex, obj => obj.id == data.id)
          this.myex.push(response.data)
          this.closeFormDialog()
        })
        .catch(error => {
          LNbits.utils.notifyApiError(error)
        })
    },
    async deleteHedge(tempId) {
      var hedge = _.findWhere(this.myex, {id: tempId})
      const wallet = _.findWhere(this.g.user.wallets, {
        id: hedge.wallet
      })
      await LNbits.utils
        .confirmDialog('Are you sure you want to delete this Hedge?')
        .onOk(function () {
          LNbits.api
            .request(
              'DELETE',
              '/hedge/api/v1/myex/' + tempId,
              wallet.adminkey
            )
            .then(() => {
              this.myex = _.reject(this.myex, function (obj) {
                return obj.id === hedge.id
              })
            })
            .catch(error => {
              LNbits.utils.notifyApiError(error)
            })
        })
    },

    async exportCSV() {
      await LNbits.utils.exportCSV(this.myexTable.columns, this.myex)
    },
    async itemsArray(tempId) {
      const hedge = _.findWhere(this.myex, {id: tempId})
      return [...hedge.itemsMap.values()]
    },
    async openformDialog(id) {
      const [tempId, itemId] = id.split(':')
      const hedge = _.findWhere(this.myex, {id: tempId})
      if (itemId) {
        const item = hedge.itemsMap.get(id)
        this.formDialog.data = {
          ...item,
          hedge: tempId
        }
      } else {
        this.formDialog.data.hedge = tempId
      }
      this.formDialog.data.currency = hedge.currency
      this.formDialog.show = true
    },
    async openUrlDialog(tempid) {
      this.urlDialog.data = _.findWhere(this.myex, {id: tempid})
      this.qrValue = this.urlDialog.data.lnurlpay

      // Connecting to our websocket fired in tasks.py
      this.connectWebocket(this.urlDialog.data.id)

      this.urlDialog.show = true
    },
    async closeformDialog() {
      this.formDialog.show = false
      this.formDialog.data = {}
    },
    async createInvoice(tempid) {
      ///////////////////////////////////////////////////
      ///Simple call to the api to create an invoice/////
      ///////////////////////////////////////////////////
      myex = _.findWhere(this.myex, {id: tempid})
      const wallet = _.findWhere(this.g.user.wallets, {id: myex.wallet})
      const data = {
        hedge_id: tempid,
        amount: this.invoiceAmount,
        memo: 'Hedge - ' + myex.name
      }
      await LNbits.api
        .request('POST', `/hedge/api/v1/myex/payment`, wallet.inkey, data)
        .then(response => {
          this.qrValue = response.data.payment_request
          this.connectWebocket(wallet.inkey)
        })
        .catch(error => {
          LNbits.utils.notifyApiError(error)
        })
    },
    connectWebocket(hedge_id) {
      //////////////////////////////////////////////////
      ///wait for pay action to happen and do a thing////
      ///////////////////////////////////////////////////
      if (location.protocol !== 'http:') {
        localUrl =
          'wss://' +
          document.domain +
          ':' +
          location.port +
          '/api/v1/ws/' +
          hedge_id
      } else {
        localUrl =
          'ws://' +
          document.domain +
          ':' +
          location.port +
          '/api/v1/ws/' +
          hedge_id
      }
      this.connection = new WebSocket(localUrl)
      this.connection.onmessage = () => {
        this.urlDialog.show = false
      }
    }
  },
  ///////////////////////////////////////////////////
  //////LIFECYCLE FUNCTIONS RUNNING ON PAGE LOAD/////
  ///////////////////////////////////////////////////
  async created() {
    await this.getHedges()
  }
})
