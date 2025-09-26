import requests
import json
import time
import os
from datetime import datetime
from utils.logger import write_log

class StockIndexFetcher:
    """A股主要指数获取工具类，带日志记录功能"""
    
    def __init__(self):
        # 指数名称与代码映射
        self.index_codes = {
            "上证指数": "000001",
            "深证成指": "399001",
            "创业板指": "399006",
            "沪深300": "000300",
            "上证50": "000016",
            "中证500": "000905",
            "科创50": "000688",
            "中小板指": "399005"
        }
        
        # 记录每个指数最近成功的数据源
        self.successful_sources = {name: None for name in self.index_codes.keys()}
        
        # 请求头信息
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36'
        }
        self.log_dir = os.path.join("logs", "index")  # logs/index
        self.log_prefix = "index_log"                # index_log_20250924.txt
    
    def _write_log(self, message: str, level: str = 'info'):
        """
        封装 write_log，自动使用 index 目录和 index_log 前缀
        :param message: 日志内容
        :param level: 日志级别，可选，默认为 'info'
        """
        # 格式化消息：[LEVEL] 内容
        full_message = f"{level.upper():<8} {message}"
        
        # ✅ 使用通用日志工具，传入自定义目录和前缀
        write_log(
            message=full_message,
            log_dir=self.log_dir,
            prefix=self.log_prefix
        )
    def _get_index_via_sina(self, index_code):
        """从新浪财经获取指数数据（内部方法）"""
        try:
            url = f"https://hq.sinajs.cn/list=s_{index_code}"
            headers = {
                'Referer': 'https://finance.sina.com.cn',
                'User-Agent': self.headers['User-Agent']
            }
            
            response = requests.get(url, headers=headers, timeout=10)
            response.encoding = 'gbk'
            
            # 解析数据
            data_str = response.text
            data_str = data_str[data_str.find('="')+2:data_str.rfind('"')]
            fields = data_str.split(',')
            
            if len(fields) >= 4:
                # 修复涨跌幅计算
                change_percent = fields[3].strip()
                if change_percent and not change_percent.endswith('%'):
                    change_percent += '%'
                    
                result = {
                    '指数名称': fields[0],
                    '当前值': fields[1],
                    '涨跌额': fields[2],
                    '涨跌幅': change_percent
                }
                self._write_log(f"新浪财经成功获取 {fields[0]} 数据: {result}")
                return result
            error_msg = '新浪API返回数据格式异常'
            self._write_log(error_msg)
            return {'错误': error_msg}
                
        except Exception as e:
            error_msg = f'新浪API请求异常: {str(e)}'
            self._write_log(error_msg)
            return {'错误': error_msg}
    
    def _get_index_via_163(self, index_code):
        """从网易财经获取指数数据（内部方法）"""
        try:
            # 网易财经代码格式处理
            if index_code.startswith('000'):
                code_163 = '0' + index_code
            else:
                code_163 = '1' + index_code
                
            url = f"http://api.money.126.net/data/feed/{code_163}"
            response = requests.get(url, headers=self.headers, timeout=10)
            response.encoding = 'utf-8'
            
            # 解析JSONP数据
            data_str = response.text
            data_str = data_str[data_str.find('(')+1:data_str.rfind(')')]
            data = json.loads(data_str)
            
            # 获取指数数据
            index_data = data.get(code_163)
            if not index_data:
                error_msg = '网易API未返回有效数据'
                self._write_log(error_msg)
                return {'错误': error_msg}
            
            # 修复涨跌幅计算
            change_percent = round(index_data['percent'] * 100, 2)
            result = {
                '指数名称': index_data['name'],
                '当前值': str(index_data['price']),
                '涨跌额': str(round(index_data['updown'], 2)),
                '涨跌幅': f"{change_percent}%"
            }
            self._write_log(f"网易财经成功获取 {index_data['name']} 数据: {result}")
            return result
                
        except Exception as e:
            error_msg = f'网易API请求异常: {str(e)}'
            self._write_log(error_msg)
            return {'错误': error_msg}
    
    def _get_index_via_eastmoney(self, index_code):
        """从东方财富API获取指数数据（内部方法）"""
        try:
            # 确定市场前缀
            secid = f"1.{index_code}" if index_code.startswith('000') else f"0.{index_code}"
                
            url = "https://push2.eastmoney.com/api/qt/stock/get"
            params = {
                "secid": secid,
                "fields": "f43,f44,f45,f46,f60,f170",
                "ut": "fa5fd1943c7b386f172d6893dbfba10b",
                "invt": "2"
            }
            
            response = requests.get(url, params=params, headers=self.headers, timeout=10)
            data = response.json()
            
            if data['data']:
                item = data['data']
                current_value = item.get('f43', 0) / 100  # 最新价
                prev_close = item.get('f60', 0) / 100     # 昨收价
                
                # 修复涨跌幅计算
                if prev_close > 0:
                    change_amount = current_value - prev_close
                    change_percent = (change_amount / prev_close) * 100
                else:
                    change_amount = item.get('f170', 0) / 100
                    change_percent = item.get('f170', 0) / 10000
                
                index_name = self.get_index_name(index_code)
                result = {
                    '指数名称': index_name,
                    '当前值': f"{current_value:.2f}",
                    '涨跌额': f"{change_amount:.2f}",
                    '涨跌幅': f"{change_percent:.2f}%"
                }
                self._write_log(f"东方财富成功获取 {index_name} 数据: {result}")
                return result
            
            error_msg = '东方财富API返回数据为空'
            self._write_log(error_msg)
            return {'错误': error_msg}
                
        except Exception as e:
            error_msg = f'东方财富API请求异常: {str(e)}'
            self._write_log(error_msg)
            return {'错误': error_msg}
    
    def get_index_name(self, index_code):
        """根据指数代码获取指数名称"""
        for name, code in self.index_codes.items():
            if code == index_code:
                return name
        return f"指数{index_code}"
    
    def get_all_indices(self):
        """获取所有常用指数的数据，优先使用最近成功的数据源"""
        results = {}
        sources = {
            'sina': self._get_index_via_sina,
            '163': self._get_index_via_163,
            'eastmoney': self._get_index_via_eastmoney
        }
        
        # 记录开始获取的日志
        self._write_log("开始批量获取指数数据")
        
        for index_name, index_code in self.index_codes.items():
            self._write_log(f"开始获取 {index_name} 数据...")
            data = None
            tried_sources = []
            
            # 优先尝试最近成功的数据源
            preferred_source = self.successful_sources[index_name]
            if preferred_source and preferred_source in sources:
                self._write_log(f"优先使用最近成功的数据源: {preferred_source}")
                data = sources[preferred_source](index_code)
                tried_sources.append(preferred_source)
                
            # 如果首选数据源失败，尝试其他数据源
            if not data or '错误' in data:
                for source_name, source_func in sources.items():
                    if source_name not in tried_sources:
                        self._write_log(f"尝试数据源 {source_name}...")
                        data = source_func(index_code)
                        tried_sources.append(source_name)
                        if data and '错误' not in data:
                            # 记录成功的数据源
                            self.successful_sources[index_name] = source_name
                            break
            
            results[index_name] = data
            time.sleep(0.3)  # 降低请求频率
            
        self._write_log("批量获取指数数据完成")
        return results
