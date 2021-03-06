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
    shutil.rmtree("Logs", ignore_errors=True)
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

def run_compose(systest, branch, local, tag, force_rebuild, rm_all=False, verbose=False):
    """ Runs necessary systemtest with docker compose """

    test_dirname = "TestCompose_{systest}".format(systest = systest)
    test_basename = systest.split('.')[0]

    adapter_base_name="-".join([tag, branch])

    # set up environment variables, to detect precice base image, that we
    # should run with and docker images location
    export_cmd = "export PRECICE_BASE=-{}; ".format(adapter_base_name)
    extra_cmd = "export SYSTEST_REMOTE={}; ".format(docker.get_namespace()) if local else ""
    compose_config_cmd = "docker-compose config && "
    compose_exec_cmd = "bash ../../silent_compose.sh {}".format('debug' if verbose else "")
    copy_cmd = "docker cp tutorial-data:/Output ."
    log_cmd = "mkdir Logs && docker-compose logs > Logs/container.log"

    commands_main = [export_cmd +
                     extra_cmd +
                     compose_config_cmd +
                     compose_exec_cmd,
                     copy_cmd, log_cmd]
    # rebuild tutorials image if needed
    if force_rebuild:
        commands_main.insert(0, "docker-compose build --no-cache")

    commands_cleanup = ["docker-compose down -v"]

    test_path = os.path.join(os.getcwd(), 'tests', test_dirname)
    with common.chdir(test_path):

        # cleanup previous results
        shutil.rmtree("Output", ignore_errors=True)
        shutil.rmtree("Logs", ignore_errors=True)

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
        elif num_diff != 0:
            raise ValueError('compare_results.sh exited with unknown code {}'.format(num_diff))
        else:
            print('TEST SUCCEEDED - Differences to referenceOutput within tolerance.')
            sys.exit(0)
    else:
        print('TEST SUCCEEDED - No difference to referenceOutput found.')
        sys.exit(0)


def build_run_compare(test, tag, branch, local_precice, force_rebuild, rm_all=False, verbose=False):
    """ Runs and compares test, using precice branch. """
    compose_tests = ["dealii-of", "of-of", "su2-ccx", "of-ccx", "of-of_np",
            "fe-fe","nutils-of", "of-ccx_fsi"]
    test_basename = test.split(".")[0]
    if local_precice:
        build_adapters(test_basename, tag, branch, local_precice, force_rebuild)
    if test_basename in compose_tests:
        run_compose(test, branch, local_precice, tag, force_rebuild, rm_all, verbose)
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


def compose_tag(docker_username, base, features, branch):
    """
    Compose a tag based on certain features of the image. Our tagging system follows this scheme:

        DOCKER_USER/BASE-FEATURES-BRANCH

    Example:
        precice/precice-ubuntu1604.home-develop
        describes an image with the following properties:

    DOCKER_USER is precice.
        I.e. image will be pushed to https://hub.docker.com/u/precice

    BASE is precice.
        I.e. the image contains a build of precice.

    FEATURES are ubuntu1604 and home.
        I.e. ubuntu1604 is used as operating system and preCICE is installed in a user directory

    BRANCH is develop.
        I.e. image is based on the source code provided at precice:develop, https://github.com/precice/precice/tree/develop.
    """
    features_list = []
    features_list.append(features.get("os"))
    features_list.append(features.get("installation"))
    if (features.get("petsc") is "yes"): features_list.append("petsc")
    if (features.get("mpich") is "yes"): features_list.append("mpich")
    features_list = list(filter(None, features_list))  # filter "None" features that might have been added by dict.get(key), if key did not exist.

    if features_list:  # list of features is not empty
        tag = docker_username.lower() + "/" + base + "-" + ".".join(features_list).lower() + '-' + branch.lower()
    else:  # list of features is empty
        tag = docker_username.lower() + "/" + base + '-' + branch.lower()
    return tag


if __name__ == "__main__":
    # Parsing flags
    parser = argparse.ArgumentParser(description='Build local.')
    parser.add_argument('-l', '--local', action='store_true', help="Use local preCICE image (default: use remote image)")
    parser.add_argument('-s', '--systemtest', type=str, help="Choose system tests you want to use",
                        choices = common.get_tests(), required = True)
    parser.add_argument('-b', '--branch', help="preCICE branch to use", default=os.environ["TRAVIS_BRANCH"] if os.environ["TRAVIS_PULL_REQUEST"] == "false" else os.environ["TRAVIS_PULL_REQUEST_BRANCH"])  # make sure that branch corresponding to system tests branch is used, if no branch is explicitly specified. If we are testing a pull request, make sure to test agains branch from which PR originated.
    parser.add_argument('-f', '--force_rebuild', nargs='+', help="Force rebuild of variable parts of docker image",
                        default = [], choices  = ["precice", "tests"])
    parser.add_argument('--base', type=str,help="Base preCICE image to use",
            default= "Ubuntu1604.home")
    parser.add_argument('-v', '--verbose', action='store_true', help="Verbose output of participant containers")
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
            args.force_rebuild, rm_all=False, verbose=args.verbose)
