import os
import shutil
import subprocess

def build_exe():
    # 清理之前的构建结果
    if os.path.exists("dist"):
        shutil.rmtree("dist")
    if os.path.exists("build"):
        shutil.rmtree("build")
    if os.path.exists("main.spec"):
        os.remove("main.spec")
    
    # 使用PyInstaller打包
    # 假设你的主程序文件名为fund_manager.py
    command = [
        "pyinstaller",
        "--name", "FVTracker",
        "--onefile",  # 生成单个EXE文件
        "--windowed",  # 不显示控制台窗口
        "--icon=FVTracker.ico",  # 可选：指定图标文件
        "--add-data=fund_data.db;.",  # 包含数据库文件
        "main.py"  # 你的主程序文件名
    ]
    
    try:
        subprocess.run(command, check=True)
        print("打包成功！EXE文件在dist目录下")
        
        # 复制数据库文件到dist目录（如果不存在）
        if not os.path.exists(os.path.join("dist", "fund_data.db")):
            if os.path.exists("fund_data.db"):
                shutil.copy2("fund_data.db", os.path.join("dist", "fund_data.db"))
                print("已复制数据库文件到dist目录")
    except subprocess.CalledProcessError as e:
        print(f"打包失败: {e}")

if __name__ == "__main__":
    build_exe()
