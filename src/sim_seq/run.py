import os
import sys


def main():
    dut_dir = "output_tb_gen_tb_20250408"
    # dut_num_list = [156]
    dut_num_list = [155,156]

    # construct DUT target
    dut_list = [
        os.path.join(dut_dir, str(dut_num), "top.v") for dut_num in dut_num_list
    ]
    test_list = [
        os.path.join(dut_dir, str(dut_num), "testbench.json")
        for dut_num in dut_num_list
    ]

    # for each DUT
    for idx, i in enumerate(dut_num_list):
        print(f"working on {i}")
        dut_path = dut_list[idx]

        os.system("mkdir -p ./logs/{}".format(i))

        # reset simulation env
        os.system("make clean > /dev/null 2>&1")
        os.system("rm -rf top_module.v")
        os.system("rm -rf testbench.json")
        # copy DUT to simulation workspace
        os.system("cp {} top_module.v".format(dut_path))
        os.system("cp {} testbench.json".format(test_list[idx]))

        # generate harness for each DUT
        os.system("python harness-generator.py")
        os.system("make")
        # 执行make命令并捕获输出

        make_output = os.popen("make 2>&1").read()

        # 解析make输出中的unpass信息
        log_file = f"{dut_dir}/{i}/make_output.log"
        # 保存make输出到日志文件
        with open(log_file, "w") as f:
            f.write(make_output)

        # 查找unpass信息
        unpass_count = make_output.count("UNPASS")

        # 将unpass结果写入总结文件
        summary_file = f"summary.txt"
        with open(summary_file, "w") as f:
            f.write(f"Total UNPASS count: {unpass_count}\n")
            if unpass_count > 0:
                f.write("Make compilation contains UNPASS results\n")
            else:
                f.write("No UNPASS found in make compilation\n")
        # 保存make输出到日志文件


if __name__ == "__main__":
    main()
