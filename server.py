"""
股票回測 API 伺服器
執行: python server.py
然後開啟瀏覽器 http://localhost:8765
"""

import http.server
import json
import urllib.parse
import os
import sys

# 加入當前目錄到路徑
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from backtest_engine import run_backtest, fetch_stock_data, run_portfolio_strategy

PORT = 8765
HTML_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'index.html')


class BacktestHandler(http.server.BaseHTTPRequestHandler):
    
    def log_message(self, format, *args):
        print(f"[{self.address_string()}] {format % args}")
    
    def send_json(self, data, status=200):
        body = json.dumps(data, ensure_ascii=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', len(body))
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(body)
    
    def send_html(self, content):
        body = content.encode('utf-8')
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.send_header('Content-Length', len(body))
        self.end_headers()
        self.wfile.write(body)
    
    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()
    
    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        
        if parsed.path == '/' or parsed.path == '/index.html':
            if os.path.exists(HTML_FILE):
                with open(HTML_FILE, 'r', encoding='utf-8') as f:
                    self.send_html(f.read())
            else:
                self.send_json({'error': 'index.html not found'}, 404)
        
        elif parsed.path == '/api/health':
            ib_installed = False
            try:
                from ib_data import is_ib_available
                ib_installed = is_ib_available()
            except Exception:
                pass
            yf_installed = False
            try:
                import yfinance
                yf_installed = True
            except ImportError:
                pass
            self.send_json({
                'status': 'ok',
                'message': '股票回測引擎運行中',
                'ib_available': ib_installed,
                'yfinance_available': yf_installed
            })
        
        else:
            self.send_json({'error': 'Not found'}, 404)
    
    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        
        content_length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(content_length)
        
        try:
            config = json.loads(body.decode('utf-8'))
        except json.JSONDecodeError:
            self.send_json({'error': '無效的 JSON 格式'}, 400)
            return
        
        if parsed.path == '/api/backtest':
            try:
                result = run_backtest(config)
                self.send_json(result)
            except Exception as e:
                self.send_json({'error': str(e)}, 500)
        
        elif parsed.path == '/api/portfolio':
            try:
                symbols_weights = config.get('symbols_weights', {})
                capital = float(config.get('capital', 100000))
                start_date = config.get('start_date', '2022-01-01')
                end_date = config.get('end_date', '2024-12-31')
                data_source = config.get('data_source', 'auto')
                
                result = run_portfolio_strategy(symbols_weights, capital, start_date, end_date,
                                                data_source=data_source)
                self.send_json(result)
            except Exception as e:
                self.send_json({'error': str(e)}, 500)
        
        elif parsed.path == '/api/stock_data':
            try:
                symbol = config.get('symbol', 'AAPL')
                start_date = config.get('start_date', '2022-01-01')
                end_date = config.get('end_date', '2024-12-31')
                data_source = config.get('data_source', 'auto')
                data = fetch_stock_data(symbol, start_date, end_date, data_source)
                self.send_json(data)
            except Exception as e:
                self.send_json({'error': str(e)}, 500)
        
        else:
            self.send_json({'error': 'Not found'}, 404)


def main():
    print("=" * 50)
    print("  📈 股票回測系統啟動中...")
    print("=" * 50)
    
    # 檢查 IB
    try:
        from ib_data import is_ib_available, IB_HOST, IB_PORT
        if is_ib_available():
            print(f"  ✅ ib_async 已安裝，可使用 IB 資料")
            print(f"     連線目標: {IB_HOST}:{IB_PORT}（請確認 TWS/Gateway 已開啟並啟用 API）")
        else:
            print("  ⚠️  ib_async 未安裝，無法使用 IB 資料")
            print("     安裝方式: pip install ib_async")
    except Exception:
        print("  ⚠️  ib_data 模組載入失敗")
    
    # 檢查 yfinance
    try:
        import yfinance
        print("  ✅ yfinance 已安裝，可使用 Yahoo Finance 資料")
    except ImportError:
        print("  ⚠️  yfinance 未安裝，將使用模擬資料")
        print("     安裝方式: pip install yfinance")
    
    print(f"\n  🌐 伺服器啟動於: http://localhost:{PORT}")
    print("  🛑 按 Ctrl+C 停止伺服器\n")
    
    server = http.server.HTTPServer(('', PORT), BacktestHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n\n  伺服器已停止。")
        try:
            from ib_data import disconnect
            disconnect()
        except Exception:
            pass


if __name__ == '__main__':
    main()
