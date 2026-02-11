<div align="center">
  <img width="80px" src="./resources/logo.png" alt="icon"/>
  <h1>FVTracker</h1>
</div>

<div style="height: 10px; clear: both;"></div>

<div align="center">
  <p>基于Python的基金估值跟踪工具。</p>
  <p>
    <a href="https://gitee.com/HTLaoYang/FVTracker" target="_blank"><img src="https://gitee.com/HTLaoYang/FVTracker/badge/star.svg" alt="Gitee"></a>
    <a href="https://gitee.com/HTLaoYang/FVTracker" target="_blank"><img src="https://gitee.com/HTLaoYang/FVTracker/badge/fork.svg" alt="Gitee-forks"></a>
    <a href="https://github.com/htlaoyang/FVTracker" target="_blank"><img src="https://img.shields.io/github/stars/htlaoyang/FVTracker" alt="Github"></a>
    <a href="https://github.com/htlaoyang/FVTracker" target="_blank"><img src="https://img.shields.io/github/forks/htlaoyang/FVTracker" alt="Github-forks"></a>
    <a href="https://www.python.org/" target="_blank"><img src="https://img.shields.io/badge/Python-3.8%2B-blue?logo=python&logoColor=white" alt="python"></a>
        <a href="./LICENSE" target="_blank"><img src="https://img.shields.io/badge/License-MIT-yellow" alt="license"></a>
  </p>
</div>


## 📋 项目概述

FVTracker 是一个基于Python的基金估值跟踪工具，接口数据来源于网上公开的API；
项目初衷主要是获取基金每天实时估值记录，用于分析及提供一些特定策略。
对于估值在底部震荡基金，提出一个分批加仓策略建议;帮助用户证验自已的操作理念或是提供回本执行计划；
仅供学习参考，投资需谨慎。
项目地址：[gitee](https://gitee.com/HTLaoYang/FVTracker)    |    [github](https://github.com/htlaoyang/FVTracker) 


## 🛠️ 技术栈

### 
- **开发语言**：Python 3.8.10
- **GUI库*****：Tkinter
- **包管理器**：pip 25.0.1

## 🏗️ 项目结构

```
root
├── utils                          # 工具
│   ├── db                         # 数据库
│      ├── database.py             # 数据库操作
│      └── db_upgrade_manager.py   # 数据库升级
│   ├── logger.py                  # 日志
│   └── stock_index_fetcher        # 指数
│   └── sys_chinese_font.py        # 字体
│   └── message_notifier.py        # 消息框
├── module                         # 功能模块
│   ├── fund_manager.py            # 基金管理模块
│   ├── fund_history_viewer.py     # 基金历史净值查询及分析模块
│   ├── FVTracker.py               # 基金监控跟踪模块
├── main.py                        # 程序入口
├── config.py                      # 常量配置
├── build_exe.py                   # 打包入口
├── FVTracker.ico                  # 国标
```

## 🚀 环境要求与安装

### 环境要求建议
- Python >= 3.8.10
- pip    >= 25.0.1 
- Git

### 使用步骤及说明

1. 克隆仓库
```bash
git clone https://gitee.com/HTLaoYang/FVTracker.git
cd FVTracker
```

2. 安装依赖
```bash
pip install -r requirements.txt
```

3. 运行
```bash
python main.py
```

4. 构建EXE执行文件
```bash
python build_exe.py
```

## 💎 功能
### 业务功能
- **基金管理****：基金信息的维护
- **设置管理****：监控的配置
- **基金监控****：基金实时净值获取、指数实时净值获取、基金历史估值查询、基金左侧加仓策略建议
- **数据库升级**：数据库自动升级

## 🖥️ 更新列表
#### 1.21更新
- 增加钛媒体新闻快讯获取及自动播报功能【增加功能】
- 增加托盘功能【增加功能】
- 基金历史估值查询、策略分析默认查询开始时间为5年前，并修正更改查询开始时间，开始时间无效。
#### 1.20更新
- 增加基金计算器工具【增加功能】
- 增加涨跌浮发送提醒邮件功能【增加功能】
#### 1.19更新
- 界面显示字体默认由12放大到14【优化功能】
- 增加一个策略分析功能，当前提供2种策略 低位加仓 、日线趋势【增加功能】
- 调整数据库连接【优化功能】
#### 1.18更新
- 基金监控列表增加汇总盈亏【增加功能】
- 修正导出后导入报错【修复BUG】
- 删除基金，基金监控列表同步刷新【增加功能】
- 重置数据库后，没有备份库及初始库 【修复BUG】


## 📸 功能截图
### 监控主界面
![fund1.png](resources/function/fund1.png)
### 基金管理
![fund2.png](resources/function/fund2.png)
### 设置
![fund3.png](resources/function/fund3.png)
### 基金历史净值查询
![fund4.png](resources/function/fund4.png)
### 基金左侧加仓策略分析
![fund5.png](resources/function/fund5.png)
### 涨跌浮发送提醒邮件功能设置
设置基金的成本及涨跌浮数值。config.json中设置接收邮箱，并启用邮件发送提醒。      
注："enabled": true   是启用
![fund5.png](resources/function/fund16.png)
![fund5.png](resources/function/fund17.png)

## 📄 许可证

[MIT License](./LICENSE)


## 📮 联系方式

- **作者**: HTLaoYang
- **邮箱**: htlaoyang@163.com
- **作者主页**: https://gitee.com/HTLaoYang

## 👏 微信交流群/合作
**加群前请先阅读一下内容：**
- 禁止内容：黄腔、暴力言论、政治话题，违者直接飞机票（踢出群）
- 问题请在群内讨论
<table>
  <tr>
    <td align="center">官方公众号</td>
  </tr>
  <tr>
    <td ><img src="./resources/screenshotwechat.png"/></td>  
  </tr>
</table>

## 🧧 捐献作者
### 都划到这了，如果我的项目对您有帮助，请赞助我吧！😊😊😊
<table>
  <tr>
    <td align="center">支付宝</td>
    <td align="center">微信</td>
  </tr>
  <tr>
    <td ><img width="450" src="./resources/screenshot/alipay.jpg"/></td>  
    <td ><img width="500" src="./resources/screenshot/wxpay.jpg"/></td>  
  </tr>
</table>

## ⭐ Star History
[![Star History Chart](https://api.star-history.com/svg?repos=HTLaoYang/FVTracker&type=Date)](https://www.star-history.com/#HTLaoYang/FVTracker&Date)
                       