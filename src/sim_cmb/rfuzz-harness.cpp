
#include "rfuzz-harness.h"
#include <vector>
#include <string>
#include <memory>
#include <iostream>
#include <verilated.h>
#include "Vtop_module.h"
#include <sstream>

int fuzz_poke() {
    int unpass_total = 0;
    int unpass = 0;
    VerilatedContext* contextp;
    Vtop_module* top;

    // Scenario: FlagDetection
        unpass = 0;
    const std::unique_ptr<VerilatedContext> contextp_0 {new VerilatedContext};
    contextp = contextp_0.get();
    top = new Vtop_module;
    top->eval();


        if (unpass == 0) {
            std::cout << "Test passed for scenario FlagDetection" << std::endl;
        } else {
            std::cout << "Test failed,unpass = " << unpass << " for scenario FlagDetection" << std::endl;
            unpass_total += unpass;
        }
    // Scenario: ZeroInsertionDetection
        unpass = 0;
    const std::unique_ptr<VerilatedContext> contextp_1 {new VerilatedContext};
    contextp = contextp_1.get();
    top = new Vtop_module;
    top->eval();


        if (unpass == 0) {
            std::cout << "Test passed for scenario ZeroInsertionDetection" << std::endl;
        } else {
            std::cout << "Test failed,unpass = " << unpass << " for scenario ZeroInsertionDetection" << std::endl;
            unpass_total += unpass;
        }
    // Scenario: ErrorDetection
        unpass = 0;
    const std::unique_ptr<VerilatedContext> contextp_2 {new VerilatedContext};
    contextp = contextp_2.get();
    top = new Vtop_module;
    top->eval();


        if (unpass == 0) {
            std::cout << "Test passed for scenario ErrorDetection" << std::endl;
        } else {
            std::cout << "Test failed,unpass = " << unpass << " for scenario ErrorDetection" << std::endl;
            unpass_total += unpass;
        }
    // Scenario: MultipleFlagSequence
        unpass = 0;
    const std::unique_ptr<VerilatedContext> contextp_3 {new VerilatedContext};
    contextp = contextp_3.get();
    top = new Vtop_module;
    top->eval();


        if (unpass == 0) {
            std::cout << "Test passed for scenario MultipleFlagSequence" << std::endl;
        } else {
            std::cout << "Test failed,unpass = " << unpass << " for scenario MultipleFlagSequence" << std::endl;
            unpass_total += unpass;
        }
    // Scenario: ResetDuringPattern
        unpass = 0;
    const std::unique_ptr<VerilatedContext> contextp_4 {new VerilatedContext};
    contextp = contextp_4.get();
    top = new Vtop_module;
    top->eval();


        if (unpass == 0) {
            std::cout << "Test passed for scenario ResetDuringPattern" << std::endl;
        } else {
            std::cout << "Test failed,unpass = " << unpass << " for scenario ResetDuringPattern" << std::endl;
            unpass_total += unpass;
        }
    // Scenario: RandomPattern0
        unpass = 0;
    const std::unique_ptr<VerilatedContext> contextp_5 {new VerilatedContext};
    contextp = contextp_5.get();
    top = new Vtop_module;
    top->eval();


        if (unpass == 0) {
            std::cout << "Test passed for scenario RandomPattern0" << std::endl;
        } else {
            std::cout << "Test failed,unpass = " << unpass << " for scenario RandomPattern0" << std::endl;
            unpass_total += unpass;
        }
    // Scenario: RandomPattern1
        unpass = 0;
    const std::unique_ptr<VerilatedContext> contextp_6 {new VerilatedContext};
    contextp = contextp_6.get();
    top = new Vtop_module;
    top->eval();


        if (unpass == 0) {
            std::cout << "Test passed for scenario RandomPattern1" << std::endl;
        } else {
            std::cout << "Test failed,unpass = " << unpass << " for scenario RandomPattern1" << std::endl;
            unpass_total += unpass;
        }
    // Scenario: RandomPattern2
        unpass = 0;
    const std::unique_ptr<VerilatedContext> contextp_7 {new VerilatedContext};
    contextp = contextp_7.get();
    top = new Vtop_module;
    top->eval();


        if (unpass == 0) {
            std::cout << "Test passed for scenario RandomPattern2" << std::endl;
        } else {
            std::cout << "Test failed,unpass = " << unpass << " for scenario RandomPattern2" << std::endl;
            unpass_total += unpass;
        }
    // Scenario: RandomPattern3
        unpass = 0;
    const std::unique_ptr<VerilatedContext> contextp_8 {new VerilatedContext};
    contextp = contextp_8.get();
    top = new Vtop_module;
    top->eval();


        if (unpass == 0) {
            std::cout << "Test passed for scenario RandomPattern3" << std::endl;
        } else {
            std::cout << "Test failed,unpass = " << unpass << " for scenario RandomPattern3" << std::endl;
            unpass_total += unpass;
        }
    // Scenario: RandomPattern4
        unpass = 0;
    const std::unique_ptr<VerilatedContext> contextp_9 {new VerilatedContext};
    contextp = contextp_9.get();
    top = new Vtop_module;
    top->eval();


        if (unpass == 0) {
            std::cout << "Test passed for scenario RandomPattern4" << std::endl;
        } else {
            std::cout << "Test failed,unpass = " << unpass << " for scenario RandomPattern4" << std::endl;
            unpass_total += unpass;
        }
    // Scenario: RandomPattern5
        unpass = 0;
    const std::unique_ptr<VerilatedContext> contextp_10 {new VerilatedContext};
    contextp = contextp_10.get();
    top = new Vtop_module;
    top->eval();


        if (unpass == 0) {
            std::cout << "Test passed for scenario RandomPattern5" << std::endl;
        } else {
            std::cout << "Test failed,unpass = " << unpass << " for scenario RandomPattern5" << std::endl;
            unpass_total += unpass;
        }
    // Scenario: RandomPattern6
        unpass = 0;
    const std::unique_ptr<VerilatedContext> contextp_11 {new VerilatedContext};
    contextp = contextp_11.get();
    top = new Vtop_module;
    top->eval();


        if (unpass == 0) {
            std::cout << "Test passed for scenario RandomPattern6" << std::endl;
        } else {
            std::cout << "Test failed,unpass = " << unpass << " for scenario RandomPattern6" << std::endl;
            unpass_total += unpass;
        }
    // Scenario: RandomPattern7
        unpass = 0;
    const std::unique_ptr<VerilatedContext> contextp_12 {new VerilatedContext};
    contextp = contextp_12.get();
    top = new Vtop_module;
    top->eval();


        if (unpass == 0) {
            std::cout << "Test passed for scenario RandomPattern7" << std::endl;
        } else {
            std::cout << "Test failed,unpass = " << unpass << " for scenario RandomPattern7" << std::endl;
            unpass_total += unpass;
        }
    // Scenario: RandomPattern8
        unpass = 0;
    const std::unique_ptr<VerilatedContext> contextp_13 {new VerilatedContext};
    contextp = contextp_13.get();
    top = new Vtop_module;
    top->eval();


        if (unpass == 0) {
            std::cout << "Test passed for scenario RandomPattern8" << std::endl;
        } else {
            std::cout << "Test failed,unpass = " << unpass << " for scenario RandomPattern8" << std::endl;
            unpass_total += unpass;
        }
    // Scenario: RandomPattern9
        unpass = 0;
    const std::unique_ptr<VerilatedContext> contextp_14 {new VerilatedContext};
    contextp = contextp_14.get();
    top = new Vtop_module;
    top->eval();


        if (unpass == 0) {
            std::cout << "Test passed for scenario RandomPattern9" << std::endl;
        } else {
            std::cout << "Test failed,unpass = " << unpass << " for scenario RandomPattern9" << std::endl;
            unpass_total += unpass;
        }

    return unpass_total;
}
