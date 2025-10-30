import os
import sys
import subprocess
from datetime import datetime

def simulate_dut_seq(output_dir):
    # 获取当前脚本的绝对路径
    current_dir = os.path.dirname(os.path.abspath(__file__))
    sim_dir = os.path.join(current_dir, "sim_seq")
    
    # 源文件路径
    dut_path = os.path.join(output_dir, "top.v")
    test_path = os.path.join(output_dir, "testbench_0.json")
    
    # 确保目标目录存在
    os.makedirs(sim_dir, exist_ok=True)
    
    # 清理和复制文件
    subprocess.run(f"cd {sim_dir} && make clean > /dev/null 2>&1", shell=True)
    subprocess.run(f"rm -f {sim_dir}/top_module.v", shell=True)
    subprocess.run(f"rm -f {sim_dir}/testbench.json", shell=True)
    
    # 复制文件到模拟工作目录
    subprocess.run(f"cp {dut_path} {sim_dir}/top_module.v", shell=True)
    subprocess.run(f"cp {test_path} {sim_dir}/testbench.json", shell=True)
    
    # 执行模拟命令并捕获输出
    cmd = f"cd {sim_dir} && python harness-generator.py && make"
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    
    # 保存输出到日志文件
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = os.path.join(output_dir, f"simulate_seq.log")
    with open(log_file, "w") as f:
        f.write(f"Command: {cmd}\n")
        f.write(f"Return code: {result.returncode}\n")
        f.write("\n=== STDOUT ===\n")
        f.write(result.stdout)
        f.write("\n=== STDERR ===\n")
        f.write(result.stderr)

def simulate_dut_cmb(output_dir):
    # 获取当前脚本的绝对路径
    current_dir = os.path.dirname(os.path.abspath(__file__))
    sim_dir = os.path.join(current_dir, "sim_cmb")
    
    # 源文件路径
    dut_path = os.path.join(output_dir, "top.v")
    test_path = os.path.join(output_dir, "testbench_0.json")
    
    # 确保目标目录存在
    os.makedirs(sim_dir, exist_ok=True)
    
    # 清理和复制文件
    subprocess.run(f"cd {sim_dir} && make clean > /dev/null 2>&1", shell=True)
    subprocess.run(f"rm -f {sim_dir}/top_module.v", shell=True)
    subprocess.run(f"rm -f {sim_dir}/testbench.json", shell=True)
    
    # 检查文件是否存在
    if not os.path.exists(dut_path):
        print(f"Error: DUT path {dut_path} does not exist")
        return
    if not os.path.exists(test_path):
        print(f"Error: Test path {test_path} does not exist")
        return
        
    # 复制文件到模拟工作目录
    subprocess.run(f"cp {dut_path} {sim_dir}/top_module.v", shell=True)
    subprocess.run(f"cp {test_path} {sim_dir}/testbench.json", shell=True)
    
    # 执行模拟命令并捕获输出
    cmd = f"cd {sim_dir} && python harness-generator.py && make"
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    
    # 保存输出到日志文件
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = os.path.join(output_dir, f"simulate_cmb.log")
    with open(log_file, "w") as f:
        f.write(f"Command: {cmd}\n")
        f.write(f"Return code: {result.returncode}\n")
        f.write("\n=== STDOUT ===\n")
        f.write(result.stdout)
        f.write("\n=== STDERR ===\n")
        f.write(result.stderr)

if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python simulate.py <output_dir> <task_number>")
        sys.exit(1)
    
    output_dir = sys.argv[1]
    task_number = int(sys.argv[2])
    
    # 根据任务类型选择模拟函数
    simulate_dut_cmb(output_dir)

        

