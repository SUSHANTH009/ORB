from Flattrade_Automation import get_token

from API.api_helper import NorenApiPy
import datetime
import logging
import time 
import pandas as pd

import numpy as np
from fyers_apiv3 import fyersModel

import os

logging.basicConfig(level=logging.DEBUG)

api = NorenApiPy()

userid = "FZ14410"
password = "Ritesh@2003"

token = get_token()
usersession=token['token']
ret = api.set_session(userid= userid, password = password, usertoken= usersession)

class ORBTradingAlgorithm:
    def __init__(self, client_id, access_token):
        self._setup_logging()
        self._initialize_trading_params()
        self._initialize_trading_state()
        self.fyers = fyersModel.FyersModel(client_id=client_id, token=access_token, is_async=False, log_path="")
        self.logger.critical(f"ORB Trading Algorithm initialized - Max Profit: ₹{self.max_daily_profit}, Max Loss: ₹{self.max_daily_loss}")
        self.logger.critical(f"Trade limits set - Max CE entries: {self.max_ce_entries}, Max PE entries: {self.max_pe_entries}")
    
    def _setup_logging(self):
        log_dir = "logs"
        if not os.path.exists(log_dir):
            os.makedirs(log_dir)
            
        today = datetime.datetime.now().strftime("%Y-%m-%d")
        log_file = os.path.join(log_dir, f"orb_trading_{today}.log")
        
        self.logger = logging.getLogger("ORBTrading")
        self.logger.setLevel(logging.INFO)
        
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        for handler in [logging.FileHandler(log_file), logging.StreamHandler()]:
            handler.setFormatter(formatter)
            self.logger.addHandler(handler)
    
    def _initialize_trading_params(self):
        # Time parameters
        self.range_start_time = "09:15:00"
        self.range_end_time = "09:22:00"
        self.today_date = datetime.datetime.now().strftime("%Y-%m-%d")
        
        # Trading parameters
        self.buffer_points = 5
        self.profit_target_amount = 3000
        self.lot_size = 75
        self.option_price_move_trigger = 5  # Option price moves up by 5 points
        self.commission_percentage = 0.25
        
        # Risk management
        self.max_daily_profit = 3000
        self.max_daily_loss = -1200
        self.max_ce_entries = 5
        self.max_pe_entries = 5
    
    def _initialize_trading_state(self):
        # ORB calculation state
        self.orb_lines_calculated = False
        self.range_identified = False
        self.high_main_line = self.low_main_line = None
        self.high_upper_buffer = self.high_lower_buffer = None
        self.low_upper_buffer = self.low_lower_buffer = None
        
        # Performance tracking
        self.processed_ticks = 0
        self.last_performance_check = time.time()
        
        # Trade tracking
        self.daily_pnl = 0
        self.trade_count = 0
        self.last_exit_minute = None
        self.ce_entries_count = self.pe_entries_count = 0
        
        # Signal tracking
        self.touched_high_main_line = self.touched_low_main_line = False
        self.high_line_touch_time = self.low_line_touch_time = None
        
        # Option chain caching
        self.option_chain_cache = {}
        self.last_option_chain_update = 0
        self.option_chain_update_interval = 2
        
        # Active trade data
        self.active_trade = False
        self.trade_option_type = self.trade_main_line_type = None
        self.trade_entry_price = self.trade_option_entry_price = None
        self.trade_strike_price = self.trade_option_symbol = None
        self.trade_stop_loss = None
        self.trade_trailing_stop_adjusted = False
        self.trade_entry_time = None
        self.last_price = self.last_option_price = None
    
    def calculate_orb_from_history(self):
        try:
            self.logger.info("Calculating ORB lines from historical data")
            
            # Fetch historical data
            data = {
                "symbol": "NSE:NIFTY50-INDEX",
                "resolution": "1",
                "date_format": 1,
                "range_from": self.today_date,
                "range_to": self.today_date,
                "cont_flag": "1"
            }
            response = self.fyers.history(data=data)
            
            if 'candles' not in response or not response['candles']:
                self.logger.error("Failed to get historical data or empty response")
                return False
            
            # Process data into DataFrame
            columns = ['datetime', 'open', 'high', 'low', 'close', 'volume']
            df = pd.DataFrame(response['candles'], columns=columns)
            df['datetime'] = pd.to_datetime(df['datetime'], unit='s') + datetime.timedelta(hours=5, minutes=30)
            df = df.drop_duplicates(subset='datetime', keep='first')

            # Filter data for the desired time range
            df_range = df[df['datetime'].apply(lambda x: 
                (x.strftime('%Y-%m-%d %H:%M:%S') >= f'{self.today_date} {self.range_start_time}') and 
                (x.strftime('%Y-%m-%d %H:%M:%S') < f'{self.today_date} {self.range_end_time}'))]
            
            if df_range.empty:
                self.logger.error(f"No data found in the specified time range ({self.range_start_time}-{self.range_end_time})")
                return False
            
            # Calculate high and low values
            self.high_main_line = np.max([
                np.max(df_range['open']), 
                np.max(df_range['high']), 
                np.max(df_range['low']), 
                np.max(df_range['close'])
            ])
            
            self.low_main_line = np.min([
                np.min(df_range['open']), 
                np.min(df_range['high']), 
                np.min(df_range['low']), 
                np.min(df_range['close'])
            ])
            
            # Set buffer levels
            self.high_upper_buffer = self.high_main_line + self.buffer_points
            self.high_lower_buffer = self.high_main_line - self.buffer_points
            self.low_upper_buffer = self.low_main_line + self.buffer_points
            self.low_lower_buffer = self.low_main_line - self.buffer_points
            
            self.range_identified = self.orb_lines_calculated = True
            
            self._log_orb_lines()
            return True
            
        except Exception as e:
            self.logger.error(f"Error calculating ORB from history: {str(e)}")
            return False
    
    def _log_orb_lines(self):
        self.logger.critical("=== ORB LINES CALCULATED ===")
        self.logger.critical(f"High Main Line: {self.high_main_line}")
        self.logger.critical(f"  - Upper Buffer: {self.high_upper_buffer}")
        self.logger.critical(f"  - Lower Buffer: {self.high_lower_buffer}")
        self.logger.critical(f"Low Main Line: {self.low_main_line}")
        self.logger.critical(f"  - Upper Buffer: {self.low_upper_buffer}")
        self.logger.critical(f"  - Lower Buffer: {self.low_lower_buffer}")
        self.logger.critical("===========================")
    
    def process_market_data(self, message):
        self._track_performance()
        
        # Only process NIFTY data
        if 'lp' not in message.keys() or message.get('t') != 'df' or message.get('tk') != '26000':
            return
        
        price = float(message.get('lp', 0))
        timestamp = int(message.get('ft', 0))
        self.last_price = price
        
        # Convert timestamp to IST time string
        ist_offset = datetime.timedelta(hours=5, minutes=30)
        dt = datetime.datetime.fromtimestamp(timestamp, tz=datetime.timezone.utc).astimezone(datetime.timezone(ist_offset))
        time_str = dt.strftime('%H:%M:%S')
        
        # Calculate ORB lines if needed
        if time_str > self.range_end_time and not self.orb_lines_calculated:
            if not self.calculate_orb_from_history():
                self.logger.critical("Failed to calculate ORB lines from history API")
                return
        
        # Process trading logic
        if time_str > self.range_end_time and self.range_identified:
            if self.active_trade:
                self._manage_active_trade(price, time_str)
            else:
                self._check_trading_signals(price, time_str)
    
    def _track_performance(self):
        self.processed_ticks += 1
        if self.processed_ticks % 100 == 0:
            current_time = time.time()
            elapsed = current_time - self.last_performance_check
            if elapsed > 0:
                ticks_per_second = 100 / elapsed
                self.logger.info(f"Performance: {ticks_per_second:.2f} ticks/second")
            self.last_performance_check = current_time

    def _check_trading_signals(self, current_price, current_time_str):
        # Check daily limits
        if self.daily_pnl >= self.max_daily_profit:
            self.logger.critical(f"DAILY MAX PROFIT REACHED (₹{self.daily_pnl:.2f}) - No new trades today")
            return
            
        if self.daily_pnl <= self.max_daily_loss:
            self.logger.critical(f"DAILY MAX LOSS REACHED (₹{self.daily_pnl:.2f}) - No new trades today")
            return
        
        # Check for main line touches
        if abs(current_price - self.high_main_line) < 0.3:
            self.touched_high_main_line = True
            self.high_line_touch_time = current_time_str
            self.logger.critical(f"{current_time_str} - Price touched HIGH Main Line: {current_price}")
        
        if abs(current_price - self.low_main_line) < 0.3:
            self.touched_low_main_line = True
            self.low_line_touch_time = current_time_str
            self.logger.critical(f"{current_time_str} - Price touched LOW Main Line: {current_price}")
        
        if self.touched_high_main_line: # Check for entry signals from HIGH main line
            if current_price > self.high_upper_buffer:
                self.logger.critical(f"{current_time_str} - Price crossed HIGH Upper Buffer: {current_price}")
                self._enter_trade("CE", "HIGH", current_price, current_time_str)
                self.touched_high_main_line = False
                return
            
            if current_price < self.high_lower_buffer:
                self.logger.critical(f"{current_time_str} - Price crossed HIGH Lower Buffer: {current_price}")
                self._enter_trade("PE", "HIGH", current_price, current_time_str)
                self.touched_high_main_line = False
                return
        
        if self.touched_low_main_line:    # Check for entry signals from LOW main line
            if current_price >= self.low_upper_buffer:
                self.logger.critical(f"{current_time_str} - Price crossed LOW Upper Buffer: {current_price}")
                self._enter_trade("CE", "LOW", current_price, current_time_str)
                self.touched_low_main_line = False
                return
            
            if current_price <= self.low_lower_buffer:
                self.logger.critical(f"{current_time_str} - Price crossed LOW Lower Buffer: {current_price}")
                self._enter_trade("PE", "LOW", current_price, current_time_str)
                self.touched_low_main_line = False
                return
    
    def _get_option_chain(self, current_nifty_price):
        current_time = time.time()
        
        if current_time - self.last_option_chain_update > self.option_chain_update_interval:
            try:
                atm_strike = round(current_nifty_price / 50) * 50
                option_symbol = f"NSE:NIFTY25515{atm_strike}CE"
                
                data = {"symbol": option_symbol, "strikecount": 50}
                response = self.fyers.optionchain(data=data)
                
                if response and 'data' in response and 'optionsChain' in response['data']:
                    self.option_chain_cache = response
                    self.last_option_chain_update = current_time
                    self.logger.info(f"Updated option chain at {datetime.datetime.now().strftime('%H:%M:%S')}")
                else:
                    self.logger.critical(f"Failed to update option chain: {response}")
            except Exception as e:
                self.logger.critical(f"Error fetching option chain: {e}")
        
        return self.option_chain_cache
    
    def _get_entry_price(self, option_type, trade_type, current_nifty_price):
        option_chain = self._get_option_chain(current_nifty_price)
        
        if not option_chain or 'data' not in option_chain or 'optionsChain' not in option_chain['data']:
            self.logger.critical("Option chain not available")
            return None
        
        try:
            diff = float('inf')
            ask = bid = strike_price = symbol = None
            
            for i in option_chain['data']['optionsChain']:
                if i['option_type'] == option_type:
                    current_diff = abs(i['ltp'] - 100)
                    if current_diff < diff:
                        diff = current_diff
                        ask = i['ask']
                        bid = i['bid']
                        strike_price = i['strike_price']
                        symbol = i['symbol']
            
            return {
                'price': ask if trade_type == 'enter' else bid,
                'strike_price': strike_price,
                'symbol': symbol
            }
        
        except Exception as e:
            self.logger.critical(f"Error finding option price: {e}")
            return None
    
    def _get_exit_price(self, option_type, trade_strike_price):
        try:
            data = {"symbols": f"NSE:NIFTY25515{trade_strike_price}{option_type}"}
            response = self.fyers.quotes(data=data)
            price = response['d'][0]['v']['bid']
            
            return {'price': price}
        
        except Exception as e:
            self.logger.critical(f"Error finding exit price: {e}")
            return None
    
    def _enter_trade(self, option_type, main_line_type, current_price, time_str):
        if (option_type == "CE" and self.ce_entries_count >= self.max_ce_entries) or \
           (option_type == "PE" and self.pe_entries_count >= self.max_pe_entries):
            self.logger.critical(f"TRADE REJECTED - Maximum {option_type} entries reached for today")
            return
        
        current_minute = time_str.split(':')[0] + ':' + time_str.split(':')[1]
        if self.last_exit_minute and current_minute == self.last_exit_minute:
            self.logger.critical(f"TRADE REJECTED - Cannot enter in same minute as previous exit ({current_minute})")
            return
        
        if self.daily_pnl >= self.max_daily_profit or self.daily_pnl <= self.max_daily_loss:
            self.logger.critical(f"TRADE REJECTED - Daily PnL limit reached (Current: ₹{self.daily_pnl:.2f})")
            return
        
        option_details = self._get_entry_price(option_type, 'enter', current_price)
        if not option_details:
            self.logger.critical("Cannot enter trade - option details not available")
            return

        # Set stop loss at 1 point below entry price
        stop_loss = option_details['price'] - 1
        
        if option_type == "CE":
            self.ce_entries_count += 1
        else:  # PE
            self.pe_entries_count += 1
        
        self.active_trade = True
        self.trade_option_type = option_type
        self.trade_main_line_type = main_line_type
        self.trade_entry_price = current_price
        self.trade_option_entry_price = option_details['price']
        self.trade_strike_price = option_details['strike_price']
        self.trade_option_symbol = option_details['symbol']
        self.trade_stop_loss = stop_loss
        self.trade_trailing_stop_adjusted = False
        self.trade_entry_time = time_str
        self.trade_count += 1
        self.last_option_price = option_details['price']
        
        self._log_trade_entry(current_price, option_details, stop_loss, time_str)
    
    def _log_trade_entry(self, current_price, option_details, stop_loss, time_str):
        self.logger.critical(f">>> TRADE ENTRY: {self.trade_option_type} at {self.trade_main_line_type} Main Line")
        self.logger.critical(f"    NIFTY Price: {current_price}")
        self.logger.critical(f"    Option Strike: {option_details['strike_price']}")
        self.logger.critical(f"    Option Symbol: {option_details['symbol']}")
        self.logger.critical(f"    Option Entry Price: {option_details['price']}")
        self.logger.critical(f"    Initial Option Stop Loss: {stop_loss}")
        self.logger.critical(f"    Time: {time_str}")
        self.logger.critical(f"    Trade count for today: {self.trade_count}")
        
        if self.trade_option_type == "CE":
            self.logger.critical(f"    CE entries used: {self.ce_entries_count}/{self.max_ce_entries}")
        else:
            self.logger.critical(f"    PE entries used: {self.pe_entries_count}/{self.max_pe_entries}")
    
    def _manage_active_trade(self, current_price, current_time_str):
        if not self.active_trade:
            return
        
        option_details = self._get_exit_price(self.trade_option_type, self.trade_strike_price)
        
        if option_details:
            current_option_price = option_details['price']
            self.last_option_price = current_option_price
            option_price_diff = current_option_price - self.trade_option_entry_price
            
            entry_commission = self.trade_option_entry_price * self.lot_size * (self.commission_percentage / 100)
            exit_commission = current_option_price * self.lot_size * (self.commission_percentage / 100)
            total_commission = entry_commission + exit_commission
            estimated_profit = (option_price_diff * self.lot_size) - total_commission
            
            # Check profit target - exit if profit reaches ₹3000
            if estimated_profit >= self.profit_target_amount:
                self._exit_trade("Take Profit - Target Amount", current_price, current_time_str, current_option_price)
                return
            
            # Adjust trailing stop loss when price moves up by 5 points
            if option_price_diff >= self.option_price_move_trigger and not self.trade_trailing_stop_adjusted:
                self.trade_stop_loss = self.trade_option_entry_price + 1
                self.trade_trailing_stop_adjusted = True
                self.logger.critical(f"{current_time_str} >>> STOP LOSS ADJUSTED: Option price gained {option_price_diff} points")
                self.logger.critical(f"    New stop loss set at: {self.trade_stop_loss}")
            
            # Exit on stop loss hit
            if current_option_price <= self.trade_stop_loss:
                self._exit_trade("Stop Loss Hit", current_price, current_time_str, current_option_price)
                return
        
    def _exit_trade(self, reason, exit_price, current_time_str, option_exit_price=None):
        if not self.active_trade:
            return
        
        self.last_exit_minute = current_time_str.split(':')[0] + ':' + current_time_str.split(':')[1]
        
        option_profit = total_commission = None
        if option_exit_price is not None:
            option_price_diff = option_exit_price - self.trade_option_entry_price
            entry_commission = self.trade_option_entry_price * self.lot_size * (self.commission_percentage / 100)
            exit_commission = option_exit_price * self.lot_size * (self.commission_percentage / 100)
            total_commission = entry_commission + exit_commission
            option_profit = (option_price_diff * self.lot_size) - total_commission
            self.daily_pnl += option_profit
        
        nifty_price_diff = abs(exit_price - self.trade_entry_price)
        exited_option_type = self.trade_option_type
        
        self._log_trade_exit(reason, exit_price, current_time_str, option_exit_price, 
                            option_profit, total_commission, nifty_price_diff, exited_option_type)
        
        self._reset_trade_state()
    
    def _log_trade_exit(self, reason, exit_price, current_time_str, option_exit_price, 
                       option_profit, total_commission, nifty_price_diff, exited_option_type):
        self.logger.critical(f"<<< TRADE EXIT: {reason}")
        self.logger.critical(f"    Option Type: {self.trade_option_type}")
        self.logger.critical(f"    Option Strike: {self.trade_strike_price}")
        self.logger.critical(f"    Option Symbol: {self.trade_option_symbol}")
        self.logger.critical(f"    Entry NIFTY Price: {self.trade_entry_price}")
        self.logger.critical(f"    Exit NIFTY Price: {exit_price}")
        self.logger.critical(f"    Entry Option Price: {self.trade_option_entry_price}")
        
        if option_exit_price:
            self.logger.critical(f"    Exit Option Price: {option_exit_price}")
            self.logger.critical(f"    Option Profit (after commission): ₹{option_profit:.2f}")
            self.logger.critical(f"    Commission charged: ₹{total_commission:.2f}")
            self.logger.critical(f"    Current Daily P&L: ₹{self.daily_pnl:.2f}")
        else:
            self.logger.critical("    Option Exit Price: Not available")
            self.logger.critical(f"    NIFTY Movement: {nifty_price_diff:.2f} points")
            
        self.logger.critical(f"    Entry Time: {self.trade_entry_time}")
        self.logger.critical(f"    Exit Time: {current_time_str}")
        self.logger.critical(f"    No new trades until after {self.last_exit_minute}")
        
        if exited_option_type == "CE":
            self.logger.critical(f"    CE entries used: {self.ce_entries_count}/{self.max_ce_entries}")
        else:
            self.logger.critical(f"    PE entries used: {self.pe_entries_count}/{self.max_pe_entries}")
        
        if self.daily_pnl >= self.max_daily_profit:
            self.logger.critical(f"DAILY MAX PROFIT REACHED (₹{self.daily_pnl:.2f}) - No more trades today")
        
        if self.daily_pnl <= self.max_daily_loss:
            self.logger.critical(f"DAILY MAX LOSS REACHED (₹{self.daily_pnl:.2f}) - No more trades today")
    
    def _reset_trade_state(self):
        self.active_trade = False
        self.trade_option_type = None
        self.trade_main_line_type = None
        self.trade_entry_price = None
        self.trade_option_entry_price = None
        self.trade_strike_price = None
        self.trade_option_symbol = None
        self.trade_stop_loss = None
        self.trade_trailing_stop_adjusted = False
        self.trade_entry_time = None


def initialize_orb_algorithm(client_id, access_token):
    return ORBTradingAlgorithm(client_id, access_token)

# Initialize the algorithm
access_token = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJhdWQiOlsiZDoxIiwiZDoyIiwieDowIiwieDoxIiwieDoyIl0sImF0X2hhc2giOiJnQUFBQUFCb0ZFN2QtcFhXWm9SNE9ISHZkU0hBeTFfVERSR1M4dlFMU05JMDFqX1ZDcGYwNjVvYnFlb1pqWjllN25kRFV5N3RoOG4zM2pTY1RjbWZCMmNoTUYxaFJvdkY3d1AzelozR0lFYWgxTE9JR0Mya2hiYz0iLCJkaXNwbGF5X25hbWUiOiIiLCJvbXMiOiJLMSIsImhzbV9rZXkiOiJiMGY1MzM1YjA5OGU0ZTIyNWY3ODM2YWUzODJlMTZlYTAyMjA0MWViZDc4M2NiNzA1NDU3MjNhYiIsImlzRGRwaUVuYWJsZWQiOiJOIiwiaXNNdGZFbmFibGVkIjoiTiIsImZ5X2lkIjoiWVMwMDM0NiIsImFwcFR5cGUiOjEwMCwiZXhwIjoxNzQ2MjMyMjAwLCJpYXQiOjE3NDYxNjEzNzMsImlzcyI6ImFwaS5meWVycy5pbiIsIm5iZiI6MTc0NjE2MTM3Mywic3ViIjoiYWNjZXNzX3Rva2VuIn0.THFI2FmRiAdN0nbuJ9xU1oGhawIyc1v9SisEC-ElhiI'
client_id = "FPC2IYNCSG-100"

orb_algorithm = initialize_orb_algorithm(client_id, access_token)

# Websocket callbacks
def on_subscribe_update(message):
    print(f"Market data update: {message}")
    orb_algorithm.process_market_data(message)

def on_order_update(message):
    print(f"Order update: {message}")
    
def on_socket_open():
    print("Socket opened! Subscribing to NIFTY 50 data...")
    api.subscribe("NSE|26000", 2)
    
def on_socket_close():
    print("Socket connection closed")
    
def on_socket_error(error):
    print(f"Socket error: {error}")

# Start the websocket
api.start_websocket(
    subscribe_callback=on_subscribe_update,
    order_update_callback=on_order_update,
    socket_open_callback=on_socket_open,
    socket_close_callback=on_socket_close,
    socket_error_callback=on_socket_error)