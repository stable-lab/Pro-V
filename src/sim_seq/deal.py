# 把output_tb_gen_tb_20250407文件夹中对应的taskid的testbench.json文件移到testcase应的taskid的文件夹中
import os
import shutil

# 获取当前目录
current_dir = os.getcwd()

# 获取output_tb_gen_tb_20250407文件夹中的所有文件
output_tb_gen_tb_20250407_dir = os.path.join(current_dir, "output_tb_gen_tb_20250407")
output_tb_gen_tb_20250407_files = os.listdir(output_tb_gen_tb_20250407_dir)

# 获取testcase文件夹中的所有文件
testcase_dir = os.path.join(current_dir, "testcase")
testcase_files = os.listdir(testcase_dir)

# 遍历output_tb_gen_tb_20250407文件夹中的所有文件
for file in output_tb_gen_tb_20250407_files:
    # 获取文件名
    file_name = os.path.basename(file)
    # 获取文件名中的taskid
    taskid = file_name
    # 在testcase文件夹中查找对应的taskid的文件
    for testcase_file in testcase_files:
        if taskid in testcase_file:
            # 如果找到，则把文件移到testcase文件夹中
            shutil.move(
                os.path.join(output_tb_gen_tb_20250407_dir, file, "testbench.json"),
                os.path.join(testcase_dir, testcase_file, "testbench.json"),
            )
            break
