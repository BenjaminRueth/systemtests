"""Script for system testing preCICE with docker and comparing output.

This script builds a docker image for an system test of preCICE.
It starts a container of the builded image and copys the output generated by the
simulation within the test to the host.
The output is compared to a reference.
It passes if files are equal, else it raises an exception.

Example:
    System test of-of and use local preCICE image

        $ python system_testing.py -s of-of -l
"""

import argparse, filecmp, os, shutil, sys
import common, docker
from subprocess import CalledProcessError
from common import call, ccall, get_test_variants, filter_tests, get_test_participants

def build(systest, tag, branch, local, force_rebuild):
    """ Builds a docker image for systest. """

    baseimage_name = "precice-{tag}-{branch}:latest".format(tag = tag, branch=branch)
    test_tag = "-".join([systest, tag, branch])

    docker.build_image(tag = test_tag,
            build_args = {"from" : docker.get_namespace() +
                baseimage_name if local
                else 'precice/' + baseimage_name},
            force_rebuild = force_rebuild)

def run(systest, tag, branch):
    """ Runs (create a container from an image) the specified systest. """
    test_tag = docker.get_namespace() + systest + "-" + tag + "-" + branch
    ccall("docker run -it -d --name " + test_tag + " " + test_tag)
    shutil.rmtree("Output", ignore_errors=True)
    ccall("docker cp " + test_tag + ":Output . ")

def build_adapters(systest, tag, branch, local, force_rebuild):
    """ Builds a docker images for a preCICE adapter, participating in tests """
    baseimage_name = "precice-{tag}-{branch}:latest".format(tag = tag, branch=branch)

    participants = get_test_participants(systest)
    docker_args = { 'tag': '',
                   'build_args': {"from": docker.get_namespace() + baseimage_name if local
                        else 'precice/' + baseimage_name },
                   'force_rebuild': force_rebuild, 
                   'dockerfile': 'Dockerfile'}

    with common.chdir(os.path.join(os.getcwd(), 'adapters')):
        for participant in participants:

            docker_args['tag'] = '-'.join([ participant, tag, branch])
            docker_args['dockerfile'] = "Dockerfile." + participant

            # skip "light-adapters" (e.g. nutils )
            if os.path.exists("Dockerfile.{}".format(participant)):
                docker.build_image(**docker_args)

def run_compose(systest, branch, local, tag, force_rebuild, rm_all):
    """ Runs necessary systemtest with docker compose """

    test_dirname = "TestCompose_{systest}".format(systest = systest)
    test_basename = systest.split('.')[0]

    adapter_base_name="-".join([tag, branch])

    # set up environment variables, to detect precice base image, that we
    # should run with and docker images location
    commands_main = ["""export PRECICE_BASE=-{base}; {extra_cmd} docker-compose config &&
                         bash ../../silent_compose.sh""".format(base =
                        adapter_base_name, extra_cmd =\
                        "export SYSTEST_REMOTE={remote};".format(
                                remote = docker.get_namespace()) if local else "" ),
                         "docker cp tutorial-data:/Output ."]
    # rebuild tutorials image if needed
    if force_rebuild:
        commands_main.insert(0, "docker-compose build --no-cache")

    commands_cleanup = ["docker-compose down -v"]

    test_path = os.path.join(os.getcwd(), 'tests', test_dirname)
    with common.chdir(test_path):

        # cleanup previous results
        shutil.rmtree("Output", ignore_errors=True)
        
        try: 
            for command in commands_main:
                ccall(command)

            #compare results
            path_to_ref = os.path.join(os.getcwd(), "referenceOutput")
            path_to_otp = os.path.join(os.getcwd(), "Output")
            comparison(path_to_ref, path_to_otp)

            if rm_all:
                for command in commands_cleanup:
                    ccall(command)

        except (CalledProcessError, IncorrectOutput)  as e: 
            # cleanup in either case
            if rm_all:
                for command in commands_cleanup:
                    ccall(command)
            # generate a report of failurs for local tests
            if local:
                raise e
            print ("TESTS FAILED WITH: {}".format(e))
            sys.exit(1)


class IncorrectOutput(Exception):
    def __init__(self, diff_files, left_only, right_only):
        self.diff_files = diff_files
        self.left_only = left_only
        self.right_only = right_only

    def __str__(self):
        s  = "Output files do not match reference\n"
        s += "Files differing               : " + str(self.diff_files) + "\n"
        s += "Files only in reference (left): " + str(self.left_only) + "\n"
        s += "Files only in output(right)   : " + str(self.right_only)
        return s



def comparison(pathToRef, pathToOutput):
    """Compares two directories

    Args:
        pathToRef (str): Path to the reference files.
        pathToOutput (str): Path to the output files.

    Raises:
        Exception: Raises IncorrectOutput when output differs from reference.
    """
    ret = common.get_diff_files(filecmp.dircmp(pathToRef, pathToOutput, ignore = [".gitkeep"]))
    if ret[0] or ret[1] or ret[2]:
        # check the results numerically now
        num_diff = call("bash ../../compare_results.sh {} {}".format(pathToRef, pathToOutput))
        if num_diff == 1:
            raise IncorrectOutput(*ret)



def build_run_compare(test, tag, branch, local_precice, force_rebuild, rm_all):
    """ Runs and compares test, using precice branch. """
    compose_tests = ["dealii-of", "of-of", "su2-ccx", "of-ccx", "of-of_np",
            "fe-fe","nutils-of", "of-ccx_fsi"]
    test_basename = test.split(".")[0]
    if local_precice:
        build_adapters(test_basename, tag, branch, local_precice, force_rebuild)
    if test_basename in compose_tests:
        run_compose(test, branch, local_precice, tag, force_rebuild, rm_all)
    else:
        # remaining, non-compose tests
        test_dirname = "Test_{systest}".format(systest=test)
        test_path = os.path.join(os.getcwd(), 'tests', test_dirname)
        with common.chdir(test_path):
            # Build
            build(test_basename, tag, branch, local_precice, force_rebuild)
            run(test_basename, tag, branch)
            # Preparing string for path
            pathToRef = os.path.join(os.getcwd(), "referenceOutput")
            pathToOutput = os.path.join(os.getcwd(), "Output")
            # Comparing
            comparison(pathToRef, pathToOutput)


if __name__ == "__main__":
    # Parsing flags
    parser = argparse.ArgumentParser(description='Build local.')
    parser.add_argument('-l', '--local', action='store_true', help="use local preCICE image (default: use remote image)")
    parser.add_argument('-s', '--systemtest', type=str, help="choose system tests you want to use",
                        choices = common.get_tests(), required = True)
    parser.add_argument('-b', '--branch', help="preCICE branch to use", default = "develop")
    parser.add_argument('-f', '--force_rebuild', nargs='+', help="Force rebuild of variable parts of docker image",
                        default = [], choices  = ["precice", "tests"])
    parser.add_argument('--base', type=str,help="Base preCICE image to use",
            default= "Ubuntu1604.home")
    args = parser.parse_args()
    # check if there is specialized dir for this version
    test_name = args.systemtest
    all_derived_tests = get_test_variants(test_name)
    test = filter_tests(all_derived_tests, 'Dockerfile.'+args.base)
    if len(test) != 1:
        raise Exception("Could not determine test to run!")
    else:
        test = test[0]
    tag = args.base.lower()
    build_run_compare(test, tag, args.branch.lower(), args.local,
            args.force_rebuild, False)
