# 测试文件 - 故意包含安全问题
import os
password = "admin123"  # hardcoded password
os.system(f"echo {password}")  # command injection
