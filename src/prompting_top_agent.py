import argparse
import json
import os
from datetime import datetime
import utils.python_call as py
from classify_circuit_type import CircuitTypeClassifier
from gen_tb import TB_Generator
from simulate import simulate_dut_cmb,simulate_dut_seq

from check_consistency import ConsistencyChecker
from utils.gen_config import Config
from utils.log_utils import get_logger, set_log_dir, switch_log_to_file
from pychecker import PyChecker
from pychecker_seq import PyChecker_SEQ
from tb_extract import TBExtractor
from testbench_parse import process_testbench, create_testbench_json, create_testbench_json_cmb,get_prob_spec
from refine_python_agent import RefinePythonAgent
from judge_for_RTL import JudgeForRTL
from sampling_filtering import compare_scenarios_seq, compare_scenarios_cmb,split_test_cases,filter_inconsistencies




logger = get_logger(__name__)


args_dict = {
    # "model": "deepseek-reasoner",
    # "model": "gpt-4o-2024-08-06",
    # "model": "gpt-4o-mini-2024-07-18",
    # "model": "gemini-2.0-flash",
    # "model": "claude-3-5-sonnet-v2@20241022",
    # "model_fixer": "gpt-4o-2024-08-06",
    # "provider": "vertexanthropic",
    # "provider": "openai",
    # "provider_fixer": "anthropic",
    # "provider_fixer": "openai",
    
    "temperature": 0,
    "top_p": 0.1,
    "temperature_sample": 1,
    "top_p_sample": 0.5,
    "max_token": 8192,
  
   "task_numbers": [1, 2, 3, 4, 5, 9, 11, 17, 18, 19, 20, 22, 23, 26, 29, 34, 35, 37, 38, 39, 41, 44, 45, 47, 48, 49, 50, 51, 53, 54, 57, 58, 61, 62, 64, 65, 67, 68, 70, 71, 73, 81, 82, 83, 84, 85, 87, 90, 91, 95, 96, 100, 101, 102, 108, 109,111, 112, 113, 114, 115, 116, 117, 119, 121, 123, 124, 125, 128, 130, 131, 132, 134, 135, 136, 138, 139, 140, 143],
    #"task_numbers": [12, 32, 40, 43, 46, 55, 56, 59, 75, 79, 88, 92, 98, 99, 106, 107, 110, 118] ,
    # "filter_instance": "Prob051|Prob052|Prob053|Prob054|Prob055|Prob101|Prob102|Prob103|Prob104|Prob105",
    # "filter_instance": "Prob092",
    # "filter_instance": "",
    "folder_path": "../verilog-eval/HDLBits/HDLBits_data_backup0304.jsonl",
    "run_identifier": "gen_tb",
    "key_cfg_path": "../key.cfg",
    "use_golden_ref": True,
    'sampling_size': 5,
    'stimuli_sampling_size': 3,
    "max_trials": 5,
    "stage": 0,
    "day": "20250408",
    "dut": False,
}




def main():
    args = argparse.Namespace(**args_dict)
    #day=args.day
    Config(args.key_cfg_path)
    switch_log_to_file()
    timestamp = "20250510"
    output_dir = f"output_tb_{args.run_identifier}_{timestamp}"
    log_dir = f"log_tb_{args.run_identifier}_{timestamp}"
    os.makedirs(output_dir, exist_ok=True)
    os.makedirs(log_dir, exist_ok=True) 
    python_correctness_list = []
    success_list=[]
    for task_number in args.task_numbers:
        output_results = []

        task_id = task_number
        output_dir_per_task = f"{output_dir}/{task_id}"
        log_dir_per_task = f"{log_dir}/{task_id}"
        os.makedirs(output_dir_per_task, exist_ok=True)
        os.makedirs(log_dir_per_task, exist_ok=True)
        set_log_dir(log_dir_per_task)
        if args.stage <=1:
            input_spec, header, module_code = get_prob_spec(args.folder_path, task_number)
            with open(f"{output_dir_per_task}/spec.txt", "w") as f:
                f.write(input_spec)
            with open(f"{output_dir_per_task}/module_header.txt", "w") as f:
                f.write(header)
            with open(f"{output_dir_per_task}/top.v", "w") as f:
                f.write(module_code)
            stimulus_python_path = os.path.join(output_dir_per_task, f"stimulus.py")
            
            tb_genarator = TB_Generator(
                model=args.model,
                max_token=8192,
                provider=args.provider,
                cfg_path=args.key_cfg_path,
                stimulus_python_path=stimulus_python_path,
                temperature=args.temperature,
                top_p=args.top_p,
            )


            tb_extractor = TBExtractor(
                    model=args.model,
                    max_token=8192,
                    provider=args.provider,
                    cfg_path=args.key_cfg_path,
                    temperature=args.temperature,
                    top_p=args.top_p,
                )
            py_checker = PyChecker(
                model=args.model,
                max_token=8192,
                provider=args.provider,
                cfg_path=args.key_cfg_path,
                temperature=args.temperature_sample,
                top_p=args.top_p_sample,
            )
            py_checker_seq = PyChecker_SEQ(
                model=args.model,
                max_token=8192,
                provider=args.provider,
                cfg_path=args.key_cfg_path,
                temperature=args.temperature_sample,
                top_p=args.top_p_sample,
            )
            circuit_type_classifier = CircuitTypeClassifier(
                model=args.model,
                max_token=8192,
                provider=args.provider,
                cfg_path=args.key_cfg_path,
                temperature=args.temperature,
                top_p=args.top_p,
            )
            refine_python_agent = RefinePythonAgent(
                model=args.model,
                max_token=8192,
                provider=args.provider,
                cfg_path=args.key_cfg_path,
                temperature=args.temperature_sample,
                top_p=args.top_p_sample,
                exp_dir=output_dir_per_task,
                task_numbers=args.task_numbers,
            )
            
            circuit_type_output_json_obj = circuit_type_classifier.run(input_spec)
            circuit_type = circuit_type_output_json_obj["classification"]
        if args.stage <= 1:
            refined_input_spec = tb_extractor.run(input_spec)
            with open(f"{output_dir_per_task}/spec.txt", "w") as f:
                f.write(refined_input_spec["revised_spec"])
            input_spec = refined_input_spec["revised_spec"]
            gen_python_code_list=[]
            for sampling_index in range(args.sampling_size):
                python_path = os.path.join(output_dir_per_task, f"pychecker_{sampling_index}.py")
                print(f"python_path: {python_path}")   
                if circuit_type == "CMB":
                    gen_python_code=py_checker.run(input_spec, header, python_path, circuit_type)
                else:
                    gen_python_code=py_checker_seq.run(input_spec, header, python_path, circuit_type)
                gen_python_code_list.append(gen_python_code)
            with open(f"{output_dir_per_task}/gen_python_code_list.txt", "w") as f:
                f.write(str(gen_python_code_list))
                
        if args.stage <= 1:
            
            
            stimulus_result = tb_genarator.run(
                        input_spec,
                        header,
                        circuit_type,
                        stimuli_sampling_size=args.stimuli_sampling_size,
                        
                    )
        
            print(f"stimulus_result: {stimulus_result}")
        if args.stage <= 2:
            
            
            
            
                # subproc_call(f"cd {output_dir_per_task}", timeout=120)
                # subproc_call(f"cd {output_dir_per_task}", timeout=120)
        
        
            for trial in range(args.max_trials):
                if args.stage <= 1:
                    for sampling_index in range(args.sampling_size):
                        output_results.append(
                            py.python_call_and_save(
                                f"{output_dir_per_task}/pychecker_{sampling_index}.py", silent=True, timeout=120
                            )
                        )

    
                    try:
                        output_str = "\n".join(str(result) for result in output_results)
                        output_file_path = os.path.join(output_dir_per_task, f"our_output.txt")
                        with open(output_file_path, "w") as output_file:
                                output_file.write(output_str)
                    except Exception as e:
                            logger.error(f"Error writing output file: {e}")
                            logger.error(f"Output results: {output_results}")
                    

                
                circuit_type = "SEQ"
                result_address = os.path.join(output_dir_per_task, f"our_output.txt")


                if circuit_type == "SEQ":
                    inconsistent_test_cases=compare_scenarios_seq(result_address)
                else:
                    inconsistent_test_cases=compare_scenarios_cmb(result_address)

                index_list=filter_inconsistencies(inconsistent_test_cases)
                print(f"index_list: {index_list}")
                if circuit_type == "CMB":
                    create_testbench_json_cmb(
                        f"{output_dir_per_task}/stimulus.json",
                        f"{output_dir_per_task}/our_output.txt",
                        index_list,
                    )
                    
                    
                else:
                    create_testbench_json(
                        f"{output_dir_per_task}/stimulus.json",
                        f"{output_dir_per_task}/our_output.txt",
                        index_list,
                    )
                
                score_list={}
                
                consistency_checker = ConsistencyChecker(args.model, args.max_token, args.provider, args.key_cfg_path, args.top_p, args.temperature, output_dir_per_task, task_number)
                with open(f"{output_dir_per_task}/gen_python_code_list.txt", "r") as f:
                    gen_python_code_list=eval(f.read())
                diff_gen_python_code_list=[]
                for idx in index_list:
                    diff_gen_python_code_list.append(gen_python_code_list[idx])
                max_score_idx,if_matches,judge_report=consistency_checker.run(diff_gen_python_code_list)
                
                print(f"max_score_idx: {max_score_idx}")
                if if_matches:
                    os.system(f"cp {output_dir_per_task}/pychecker_{max_score_idx}.py {output_dir_per_task}/pychecker_{0}.py")
                    break
                refine_python_agent = RefinePythonAgent(
                model=args.model,
                max_token=8192,
                provider=args.provider,
                cfg_path=args.key_cfg_path,
                temperature=args.temperature_sample,
                top_p=args.top_p_sample,
                exp_dir=output_dir_per_task,
                    task_numbers=args.task_numbers,
                )
                with open(f"{output_dir_per_task}/spec.txt", "r") as f:
                    input_spec=f.read()
                select_python_code=gen_python_code_list[0]
                gen_python_code_list=[]
                for idx in range(args.sampling_size):
                    refined_python_code,python_body=refine_python_agent.run(circuit_type,input_spec, select_python_code,judge_report)
                    with open(f"{output_dir_per_task}/pychecker_{idx}.py", "w") as f:
                        f.write(refined_python_code)
                    gen_python_code_list.append(python_body)
                with open(f"{output_dir_per_task}/gen_python_code_list.txt", "w") as f:
                    f.write(str(gen_python_code_list))


        if args.stage <= 3:
            
            if circuit_type == "CMB":
                simulate_dut_cmb(output_dir_per_task)
            else:
                simulate_dut_seq(output_dir_per_task)
            with open(f"{output_dir_per_task}/simulate_seq.log", "r") as f:
                simulate_seq_result=f.read()
            if "Unpass: 0" in simulate_seq_result:
                success_list.append(task_number)
        
        
        
            
            

            
        

    # summary.sort()
    # with open(summary_file_path, "a") as summary_file:
    #    summary_file.writelines(summary)
    print(f"success_list: {success_list}")
    with open(f"success_list.txt", "w") as f:
        f.write(str(success_list))

if __name__ == "__main__":
    main()
