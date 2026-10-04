"""
Interactive Brokers 資料抓取模組
需求：
  1. TWS 或 IB Gateway 執行中，且已啟用 API（Enable ActiveX and Socket Clients）
  2. pip install ib_async   （ib_insync 的維護版，API 相同）

連接埠對照：
  TWS 模擬帳戶: 7497   TWS 真實帳戶: 7496
  Gateway 模擬: 4002   Gateway 真實: 4001
"""

from datetime import datetime

# 連線設定（可依需要修改）
IB_HOST = '127.0.0.1'
IB_PORT = 4001        # IB Gateway 模擬帳戶預設埠
                      # TWS 模擬 7497 / TWS 真實 7496 / Gateway 真實 4001
IB_CLIENT_ID = 17     # 任意不重複的整數即可

_ib_connection = None


def _get_ib_module():
    """優先使用 ib_async（維護中），退回 ib_insync（已停止維護但仍可用）"""
    try:
        import ib_async as ibm
        return ibm
    except ImportError:
        pass
    try:
        import ib_insync as ibm
        return ibm
    except ImportError:
        return None


def is_ib_available() -> bool:
    """檢查是否已安裝 IB 套件"""
    return _get_ib_module() is not None


def _install_safety_guard(ib):
    """
    安全防呆機制：連線後立即封鎖所有下單/改單/取消單相關函式。
    就算程式碼未來被誤改而呼叫到這些函式，也只會在本機端拋出例外，
    不會真的傳送到 IB 伺服器。這是「Read-Only API」設定之外的第二道防線。
    """
    blocked_methods = [
        'placeOrder', 'cancelOrder', 'reqGlobalCancel',
        'exerciseOptions', 'placeOrders'
    ]
    for method_name in blocked_methods:
        if hasattr(ib, method_name):
            def _blocked(*args, __name=method_name, **kwargs):
                raise RuntimeError(
                    f'🛑 安全防呆已攔截：本程式僅供歷史資料查詢，'
                    f'已封鎖 {__name}() 呼叫，不會傳送至 IB 伺服器。'
                )
            setattr(ib, method_name, _blocked)


def _connect(ibm):
    """建立（或重用）IB 連線"""
    global _ib_connection
    if _ib_connection is not None and _ib_connection.isConnected():
        return _ib_connection

    ib = ibm.IB()
    ib.connect(IB_HOST, IB_PORT, clientId=IB_CLIENT_ID, timeout=10)
    _install_safety_guard(ib)   # 連線後立即上鎖，禁止下單類操作
    _ib_connection = ib
    return ib


def _make_contract(ibm, symbol: str):
    """
    根據代碼建立合約。
    - 美股: 'AAPL' → Stock('AAPL', 'SMART', 'USD')
    - 台股: '2330.TW' → Stock('2330', 'TWSE', 'TWD')  ※需有台股行情權限
    - 也支援 'SYMBOL@EXCHANGE:CURRENCY' 自訂格式，如 '7203@TSEJ:JPY'
    """
    if '@' in symbol:
        # 自訂格式 SYMBOL@EXCHANGE:CURRENCY
        sym, rest = symbol.split('@', 1)
        if ':' in rest:
            exchange, currency = rest.split(':', 1)
        else:
            exchange, currency = rest, 'USD'
        return ibm.Stock(sym, exchange, currency)

    if symbol.upper().endswith('.TW'):
        return ibm.Stock(symbol[:-3], 'TWSE', 'TWD')

    if symbol.upper().endswith('.TWO'):  # 櫃買
        return ibm.Stock(symbol[:-4], 'TWSE', 'TWD')

    return ibm.Stock(symbol, 'SMART', 'USD')


def _duration_string(start_date: str, end_date: str) -> str:
    """把日期區間換算成 IB 的 durationStr 格式"""
    start = datetime.strptime(start_date, '%Y-%m-%d')
    end = datetime.strptime(end_date, '%Y-%m-%d')
    days = (end - start).days

    if days <= 0:
        days = 1
    if days <= 365:
        return f'{days} D'
    years = (days // 365) + 1
    return f'{years} Y'


def fetch_ib_data(symbol: str, start_date: str, end_date: str) -> dict:
    """
    從 IB 抓取日線歷史資料。
    會自動嘗試多種 whatToShow 參數，並捕捉 IB 回傳的真實錯誤訊息。
    """
    ibm = _get_ib_module()
    if ibm is None:
        raise RuntimeError('未安裝 ib_async（pip install ib_async）')

    ib = _connect(ibm)

    # --- 捕捉 IB 的錯誤事件，方便診斷 ---
    ib_errors = []

    def _on_error(reqId, errorCode, errorString, contract=None):
        # 2100~2200 多為資訊性訊息（例如農場連線通知），不算錯誤
        if errorCode < 2100 or errorCode > 2200:
            ib_errors.append(f'[{errorCode}] {errorString}')

    try:
        ib.errorEvent += _on_error
    except Exception:
        pass

    try:
        contract = _make_contract(ibm, symbol)
        qualified = ib.qualifyContracts(contract)
        if not qualified:
            raise ValueError(
                f'無法識別合約 {symbol}。'
                + (f' IB 訊息：{"; ".join(ib_errors)}' if ib_errors else '')
            )
        contract = qualified[0]

        # 結束日期不能超過今天（IB 對未來日期會回傳空資料）
        end_dt_obj = datetime.strptime(end_date, '%Y-%m-%d')
        today = datetime.now()
        is_end_today = end_dt_obj.date() >= today.date()
        if end_dt_obj > today:
            end_dt_obj = today

        # IB 新版 API 要求 endDateTime 帶時區格式
        end_dt = end_dt_obj.strftime('%Y%m%d-23:59:59')
        duration = _duration_string(start_date, end_date)

        # 依序嘗試不同的資料類型：
        #   ADJUSTED_LAST — 還原股價（含股息調整，最適合回測）
        #                   ⚠️ IB 限制：此模式不支援指定 endDateTime（Error 321），
        #                      只能抓到「今天為止」的資料，故僅在結束日=今天時使用
        #   TRADES        — 成交價（未還原股息，可指定任意結束日期，通用性最高）
        #   MIDPOINT      — 中間價（不需成交行情權限，最後手段）
        attempts = []
        if is_end_today:
            # 結束日期是今天 → 可用 ADJUSTED_LAST（endDateTime 必須留空）
            attempts.append(('ADJUSTED_LAST', ''))
        attempts.append(('TRADES', end_dt))
        attempts.append(('MIDPOINT', end_dt))

        bars = None
        used_what = None
        attempt_log = []

        for what_to_show, end_param in attempts:
            ib_errors.clear()
            try:
                bars = ib.reqHistoricalData(
                    contract,
                    endDateTime=end_param,
                    durationStr=duration,
                    barSizeSetting='1 day',
                    whatToShow=what_to_show,
                    useRTH=True,
                    formatDate=1,
                    timeout=60
                )
            except Exception as e:
                attempt_log.append(f'{what_to_show}: {e}')
                bars = None

            if bars:
                used_what = what_to_show
                break

            msg = '; '.join(ib_errors) if ib_errors else '回傳空資料'
            attempt_log.append(f'{what_to_show}: {msg}')

        if not bars:
            raise ValueError(
                f'IB 未回傳 {symbol} 的資料。嘗試記錄：\n  '
                + '\n  '.join(attempt_log)
                + '\n提示：請確認 (1) 歷史資料農場已連線 (2) 帳戶有該市場行情權限 '
                  '(3) 日期區間內有交易日'
            )

        # 過濾出使用者指定的日期區間
        start = datetime.strptime(start_date, '%Y-%m-%d').date()
        end = end_dt_obj.date()

        dates, opens, highs, lows, closes, volumes = [], [], [], [], [], []
        for bar in bars:
            if hasattr(bar.date, 'year'):
                bar_date = bar.date.date() if hasattr(bar.date, 'hour') else bar.date
            else:
                bar_date = datetime.strptime(str(bar.date)[:10].replace('-', ''), '%Y%m%d').date()

            if bar_date < start or bar_date > end:
                continue
            dates.append(bar_date.strftime('%Y-%m-%d'))
            opens.append(round(float(bar.open), 4))
            highs.append(round(float(bar.high), 4))
            lows.append(round(float(bar.low), 4))
            closes.append(round(float(bar.close), 4))
            volumes.append(int(bar.volume) if bar.volume and bar.volume > 0 else 0)

        if not closes:
            raise ValueError(
                f'{symbol} 在 {start_date} ~ {end_date} 區間內沒有資料'
                f'（IB 共回傳 {len(bars)} 根 K 棒，但都在指定區間之外）'
            )

        return {
            'dates': dates,
            'close': closes,
            'open': opens,
            'high': highs,
            'low': lows,
            'volume': volumes,
            'source': 'ib',
            'ib_data_type': used_what,
            'adjusted': used_what == 'ADJUSTED_LAST'
        }

    finally:
        try:
            ib.errorEvent -= _on_error
        except Exception:
            pass


def disconnect():
    """關閉 IB 連線（伺服器關閉時呼叫）"""
    global _ib_connection
    if _ib_connection is not None and _ib_connection.isConnected():
        _ib_connection.disconnect()
    _ib_connection = None
