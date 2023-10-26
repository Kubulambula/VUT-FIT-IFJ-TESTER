#!/usr/bin/env python3

# I know that this code is trash, but you can cry about it and write yout own tester.

import sys
import os	
import getopt
import subprocess


HELP = """NAME:
	IFJ Tester

SYNOPSIS:
	test.py [OPTIONS]... [TEST]...

DESCRIPTION:
	Test script for IFJ at VUT FIT.
	Created for IFJ23, but should work for all subsequent IFJ versions.

	Arguments should be supplies
	-h, --h
		Shows this help page.
	-d, --dir=DIRECTORY
		Path to directory which is scanned for tests.
		If left empty, '$(pwd)/tests/' is used.
	-l, --list
		Shows the list of all available tests.
		Dependant on value of --dir.
		Use this option AFTER --dir. If this option is used before --dir, '$(pwd)/tests/' is always used.
	-c, --compiler-path
		Path to the IFJ compiler used for testing.
		This is the executable, that you make (just in case you didn't figure that out yet).
	-C, --compiler-timeout
		Time after the compiler test automatically fails.
	-i, --interpreter-path
		Path to the IFJ interpreter used for testing.
		This it the executable you get
	-I, --interpreter-timeout
		Time after the interpreter test automatically fails.
	-v, --verbose
		If this option is used, additional information will be printed.
	[TEST]
		Test names, that should be run separated by space.
		The test names corespond to directory names in which the tests are located.
		If left empty, all availabel tests will be run.

HOW IT WORKS:
	This script accesses tests in --dir which is a directory of directories (test categories).
	In each of these directories is another directory (test name). This directory contains following files:

		- code.ifj - MANDATORY
			The source code that is used for compilation and testing.
			If it does no exist, the test is not recognized.
		
		- stdin - OPTIONAL
			The stdin for the interpreter of compiled code.ifj.
			If it does not exist, no input is passed.
		
		- stdout - OPTIONAL
			The expected stdout of the interpreter running compiled code.ifj.
			If left empty, no stdout is expected.
		
		- return - OPTIONAL
			The expected return codes for compiler and interpreter (in this order).
			Must be int values on separate lines.
			If expected interpreter code is -1, that means, that interpreter check should be skipped.
		
		- code.ifjcode - GENERATED
			The compiled code.ifj used as a temporary file for the interpreter.

RETURN CODES:
	0	OK
	1	Argument error

AUTHOR:
	Jakub Janšta 2023
"""

WHITE = "\x1b[37m"
RED = "\x1b[31m"
GREEN = "\x1b[32m"
BLUE = "\x1b[36m"
YELLOW = "\x1b[33m"

DEFAULT_COMPILER_TIMEOUT = 10
DEFAULT_INTERPRETER_TIMEOUT = 10

# Global variable for cool boyz B)
VERBOSE = False


def get_all_subdirectories(dir):
	return [f.path for f in os.scandir(dir) if f.is_dir()] if os.path.exists(dir) else []


def normalize_path(path):
	return os.path.normpath(path).replace("\\", "/") 


# Yes, this is stupid, stfu
def get_all_tests(from_dir):
	if len(test_categories := get_all_subdirectories(from_dir)) == 0:
		print(RED + "No tests categories found..." + WHITE)
		return {}

	tests = {}
	at_least_one_test_case_found = False
	for category in test_categories:
		if len(test_cases := get_all_subdirectories(category)) == 0:
			continue
		
		tests[normalize_path(category).split("/")[-1]] = {}
		for test_case in test_cases:
			if os.path.isfile(test_case + "/code.ifj"):
				at_least_one_test_case_found = True
				tests[normalize_path(category).split("/")[-1]][normalize_path(test_case).split("/")[-1]] = normalize_path(test_case)

	if not at_least_one_test_case_found:
		print(RED + "No tests cases found..." + WHITE)
		return {}

	return tests


def get_tests_to_be_run(args, test_dir):
	all_tests = get_all_tests(test_dir)
	tests_to_be_run = []
	
	for arg in args:
		arg = list(a for a in arg.split("/") if len(a))
		if len(arg) == 1:
			if arg[0] in all_tests.keys():
				for key in all_tests[arg[0]].keys():
					tests_to_be_run.append(all_tests[arg[0]][key])
		elif len(arg) == 2:
			if arg[0] in all_tests.keys() and arg[1] in all_tests[arg[0]]:
				tests_to_be_run.append(all_tests[arg[0]][arg[1]])
		else:
			print(RED + "No test or test category matching '" +  arg.join("/") + "' found.")

	if len(tests_to_be_run) == 0:
		for test_category in all_tests.keys():
			for test_case in all_tests[test_category].keys():
				tests_to_be_run.append(all_tests[test_category][test_case])
	
	return tests_to_be_run


def get_expected_return_codes_for(test):
	try:
		f = open(test + "/return", "r")
		# get all lines and filter out empty ones
		expected_return_codes = tuple(item for item in f.read().split("\n") if len(item))
		f.close()
	except FileNotFoundError:
		if VERBOSE:
			print("	Cannot find '" + "/".join(test.split("/")[-2::]) + "/return'. Return code 0 is expected for compiler and interpreter...")
		return (0, 0)
	if len(expected_return_codes) == 0:
		if VERBOSE:
			print("	'" + "/".join(test.split("/")[-2::]) + "/return' is empty. Return code 0 is expected for compiler and interpreter...")
		return (0, 0)
	elif len(expected_return_codes) == 1:
		try:
			to_return = (int(expected_return_codes[0]), 0)
			if VERBOSE:
				print("	'" + "/".join(test.split("/")[-2::]) + "/return' is missing expected interpreter return code. Return code 0 is expected...")
		except:
			to_return = (0, 0)
			if VERBOSE:
				print("	'" + "/".join(test.split("/")[-2::]) + "/return' is in bad format. Return code 0 is expected for compiler and interpreter...")
		finally:
			return to_return
	
	try:
		to_return = (int(expected_return_codes[0]), int(expected_return_codes[1]))
	except:
		to_return = (0, 0)
		if VERBOSE:
			print("	'" + "/".join(test.split("/")[-2::]) + "/return' is in bad format. Return code 0 is expected for compiler and interpreter...")
	finally:
		return to_return


def run_tests(tests_to_be_run, compiler_path, interpreter_path, compiler_timeout=DEFAULT_COMPILER_TIMEOUT, interpreter_timeout=DEFAULT_INTERPRETER_TIMEOUT):
	tests_passed = 0
	tests_aborted = 0
	for test in tests_to_be_run:
		test_result = run_test(test, compiler_path, interpreter_path, compiler_timeout, interpreter_timeout)
		if test_result is None:
			tests_aborted += 1
			continue
		if test_result == True:
			tests_passed += 1
			print("[" + GREEN + " OK " + WHITE + "] " + "/".join(test.split("/")[-2::]))
	
	passed_percentage = round(100 * tests_passed / max(len(tests_to_be_run), 1))
	percentage_color = GREEN if passed_percentage > 75.0 else YELLOW if passed_percentage > 50.0 else RED
	print("\nSummary:	" + percentage_color + str(passed_percentage) + "%" + WHITE)
	print(BLUE + "TOTAL:		" + WHITE + str(len(tests_to_be_run)))
	print(GREEN + "PASSED:		" + WHITE + str(tests_passed))
	print(RED + "FAILED:		" + WHITE + str(len(tests_to_be_run) - tests_passed - tests_aborted))
	print(YELLOW + "ABORTED:	" + WHITE + str(tests_aborted))
	

def run_test(test_to_be_run, compiler_path, interpreter_path, compiler_timeout, interpreter_timeout):
	if VERBOSE:
		print(BLUE + "\nRunning" + WHITE + ": " + "/".join(test_to_be_run.split("/")[-2::]))
	
	expected_return_codes = get_expected_return_codes_for(test_to_be_run)

	# Run compiler
	compiler_result = run_compiler(test_to_be_run, compiler_path, compiler_timeout)
	if compiler_result["code"] is None:
		return None
	if compiler_result["code"] != expected_return_codes[0]:
		print("[" + RED + "FAIL" + WHITE + "] " + "/".join(test_to_be_run.split("/")[-2::]) + " - Compiler return code '" + str(compiler_result["code"]) + "' does not math the expected return code '" + str(expected_return_codes[0]) + "'.")
		return False
	if expected_return_codes[0] != 0:
		if VERBOSE:
			print("	Compiler failed as expected. Test considered as succesful without running interpreter...")
		# Expected code was not 0 - compiler failed as expected => so we report succesful test and don't run the interpreter
		return True

	# Run interpreter
	if expected_return_codes[1] == -1:
		if VERBOSE:
			print("	Interpreter skipped because of expected return code '-1'. Considering test as passed...")
		return True
	if len(interpreter_path) == 0:
		if VERBOSE:
			print("	Interpreter path was not specified. Considering test as passed...")
		return True
	interpreter_result = run_interpreter(test_to_be_run, interpreter_path, interpreter_timeout, compiler_result["stdout"])
	if interpreter_result["code"] is None:
		# Interpreter failed
		return None
	if interpreter_result["code"] != expected_return_codes[1]:
		print("[" + RED + "FAIL" + WHITE + "] " + "/".join(test_to_be_run.split("/")[-2::]) + " - Interpreter return code '" + str(interpreter_result["code"]) + "' does not math the expected return code '" + str(expected_return_codes[1]) + "'.")
		return False
	if expected_return_codes[1] != 0:
		if VERBOSE:
			print("	Interpreter failed as expected. Test considered as succesful without stdout checks...")
		return True
	# Test matching interpreter stdout
	try:
		interpreter_result["stdout"] = interpreter_result["stdout"].decode("utf-8")
		f = open(test_to_be_run + "/stdout")
		expected_stdout = f.read()
		f.close()
		is_ok = interpreter_result["stdout"] == expected_stdout
		if not is_ok:
			print("[" + RED + "FAIL" + WHITE + "] " + "/".join(test_to_be_run.split("/")[-2::]) + " - Interpreter stdout and expected stdout do not match.")
			if VERBOSE:
				print("<<<" + BLUE + "Exected stdout START" + WHITE + ">>>\n" + expected_stdout + "\n<<<" + BLUE + "Expected stdout END" + WHITE + ">>>")
				print("<<<" + BLUE + "Interpreter stdout START" + WHITE + ">>>\n" + interpreter_result["stdout"] +  "\n<<<" + BLUE + "Interpreter stdout END" + WHITE + ">>>")
		return is_ok
	except FileNotFoundError:
		if VERBOSE:
			print("	" + test_to_be_run + "/stdout was not found. Considering stdout to be matching...")
		return True


def run_compiler(test_to_be_run, compiler_path, compiler_timeout):
	if len(compiler_path) == 0:
		print("[" + YELLOW + "ABRT" + WHITE + "] " + "/".join(test_to_be_run.split("/")[-2::]) + " - Compiler path was not specified.")
		return {
			"code": None,
			"stdout": "",
			"stderr": ""
		}
	# Read code
	try:
		f = open(test_to_be_run + "/code.ifj", "r")
		code = f.read()
		f.close()
	except OSError:
		print("[" + YELLOW + "ABRT" + WHITE + "] " + "/".join(test_to_be_run.split("/")[-2::]) + " - Cannot open code file '" + test_to_be_run + "'.")
		return {
			"code": None,
			"stdout": "",
			"stderr": ""
		}
	# Start compiler process
	try:
		compiler_process = subprocess.Popen([compiler_path], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
	except Exception as e:
		print("[" + YELLOW + "ABRT" + WHITE + "] " + "/".join(test_to_be_run.split("/")[-2::]) + " - Cannot run compiler. " + str(e))
		return {
			"code": None,
			"stdout": "",
			"stderr": ""
		}
	# Send the compiler data to stdin
	try:
		compiler_stdout, compiler_stderr = compiler_process.communicate(str.encode(code), timeout=compiler_timeout)
		return {
			"code": compiler_process.returncode,
			"stdout": compiler_stdout,
			"stderr": compiler_stderr
		}
	except subprocess.TimeoutExpired as e:
		compiler_process.kill()
		print("[" + YELLOW + "TIME" + WHITE + "] " + "/".join(test_to_be_run.split("/")[-2::]) + " - Test timed out while compiling after " + str(e.timeout) + " seconds.")
		return {
			"code": None,
			"stdout": "",
			"stderr": ""
		}


def run_interpreter(test_to_be_run, interpreter_path, interpreter_timeout, compiler_stdout=""):
	# Start interpreter process
	try:
		interpreter_process = subprocess.Popen([interpreter_path, test_to_be_run + "/code.ifjcode"], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
	except Exception as e:
		print("[" + YELLOW + "ABRT" + WHITE + "] " + "/".join(test_to_be_run.split("/")[-2::]) + " - Cannot run interpreter. " + str(e))
		return {
			"code": None,
			"stdout": "",
			"stderr": ""
		}
	# Create file for compiled code
	try:
		f = open(test_to_be_run + "/code.ifjcode", "w")
		f.write(compiler_stdout.decode("utf-8"))
		f.close()
	except Exception as e:
		print("[" + YELLOW + "ABRT" + WHITE + "] " + "/".join(test_to_be_run.split("/")[-2::]) + " - Cannot save compiled code to disk. " + str(e))
		return {
			"code": None,
			"stdout": "",
			"stderr": ""
		}
	# Send stdin to the interpreter stdin
	try:
		f = open(test_to_be_run + "/stdin", "r")
		stdin = f.read()
		f.close()
	except FileNotFoundError:
		if VERBOSE:
			print("	Cannot read stdin. Passing an empty file...")
		stdin = ""
	try:
		interpreter_stdout, interpreter_stderr = interpreter_process.communicate(stdin.encode("utf-8"), timeout=interpreter_timeout)
		return {
			"code": interpreter_process.returncode,
			"stdout": interpreter_stdout,
			"stderr": interpreter_stderr
		}
	except subprocess.TimeoutExpired as e:
		interpreter_process.kill()
		print("[" + YELLOW + "TIME" + WHITE + "] " + test_to_be_run.split("/")[-2:-1].join("/") + " - Test timed out while interpreting after " + str(e.timeout) + " seconds.")
		return {
			"code": None,
			"stdout": "",
			"stderr": ""
		}


def main():
	try:
		# opts - (option, arg)
		# args - remaining non-option args
		opts, args = getopt.getopt(sys.argv[1:], "hd:lc:C:i:I:v", ["help", "dir=", "list", "compiler-path=", "compiler-timeout=", "interpreter-path=", "interpreter-timeout=", "verbose"])
	except:
		print(RED + "Argument error" + WHITE)
		sys.exit(1)
	
	test_dir = os.getcwd() + "/tests/"
	compiler_path = ""
	compiler_timeout = DEFAULT_COMPILER_TIMEOUT
	interpreter_path = ""
	interpreter_timeout = DEFAULT_INTERPRETER_TIMEOUT

	# opt - name of the option
	# arg - the value of the option
	for opt, arg in opts:
		if opt in ["-h", "--help"]:
			print(HELP)
			sys.exit(0)
		elif opt in ["-d", "--dir"]:
			test_dir = arg
		elif opt in ["-l", "--list"]:
			print("Available tests:")
			tests = get_all_tests(test_dir)
			for test_category in tests.keys():
				print("\t" + test_category + ":")
				for test_case in tests[test_category].keys():
					print("\t\t" + test_category + "/" + test_case)
			sys.exit(0)
		elif opt in ["-c", "--compiler-path"]:
			compiler_path = arg
		elif opt in ["-i", "--interpreter-path"]:
			interpreter_path = arg
		elif opt in ["-C", "--compiler-timeout"]:
			try:
				compiler_timeout = float(arg)
			except:
				compiler_timeout = DEFAULT_COMPILER_TIMEOUT
		elif opt in ["-I", "--interpreter-timeout"]:
			try:
				interpreter_timeout = float(arg)
			except:
				interpreter_timeout = DEFAULT_INTERPRETER_TIMEOUT
		elif opt in ["-v", "--verbose"]:
			global VERBOSE
			VERBOSE = True
	
	run_tests(get_tests_to_be_run(args, test_dir), compiler_path, interpreter_path, compiler_timeout, interpreter_timeout)
	

# public static void main(String[] args){
# 	main()
# }
if __name__ == "__main__":
	main()
