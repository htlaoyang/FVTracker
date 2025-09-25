<div align="center">
  <img src="https://gitee.com/HTLaoYang/FVTracker/blob/master/resources/logo.png" width="160">
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
git clone git clone https://gitee.com/HTLaoYang/FVTracker.git
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



## 📄 许可证

[MIT License](./LICENSE)


## 📮 联系方式

- **作者**: HTLaoYang
- **邮箱**: htlaoyang@163.com
- **作者主页**: https://gitee.com/HTLaoYang


