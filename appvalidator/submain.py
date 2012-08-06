import logging
import os
import signal
from zipfile import BadZipfile
from zlib import error as zlib_error

from .webapp import detect_webapp
from .zip import ZipPackage
from . import decorator

from constants import *

types = {0: "Unknown",
         1: "Extension/Multi-Extension",
         2: "Theme",
         3: "Dictionary",
         4: "Language Pack",
         5: "Search Provider"}

assumed_extensions = {"jar": PACKAGE_THEME,
                      "xml": PACKAGE_SEARCHPROV}

log = logging.getLogger()


class ValidationTimeout(Exception):

    def __init__(self, timeout):
        self.timeout = timeout

    def __str__(self):
        return "Validation timeout after %d seconds" % self.timeout


def prepare_package(err, path, timeout=None):
    """Prepares a file-based package for validation.

    timeout is the number of seconds before validation is aborted.
    If timeout is -1 then no timeout checking code will run.
    """
    if not timeout:
        timeout = 60  # seconds

    # Test that the package actually exists. I consider this Tier 0
    # since we may not even be dealing with a real file.
    if not os.path.isfile(path):
        err.error(
            err_id=("main", "prepare_package", "not_found"),
            error="The package could not be found")
        return

    # Pop the package extension.
    package_extension = os.path.splitext(path)[1]
    package_extension = package_extension.lower()

    if package_extension == ".webapp":
        return test_webapp(err, path)

    validation_state = {'complete': False}
    def timeout_handler(signum, frame):
        if validation_state['complete']:
            # There is no need for a timeout. This might be the result of
            # sequential validators, like in the test suite.
            return
        ex = ValidationTimeout(timeout)
        log.error("%s; Package: %s" % (str(ex), path))
        raise ex

    with open(path, "rb") as package:
        if timeout != -1:
            signal.signal(signal.SIGALRM, timeout_handler)
            signal.setitimer(signal.ITIMER_REAL, timeout)
        output = test_package(err, package, path)

    validation_state['complete'] = True

    return output


def test_webapp(err, package):
    "Tests the package to see if it is a webapp."

    detect_webapp(err, package)
    err.set_type(PACKAGE_WEBAPP)


def test_package(err, file_, name):
    "Begins tests for the package."

    # Load up a new instance of a package.
    try:
        package = ZipPackage(file_, mode="r", name=name)
    except IOError:
        # Die on this one because the file won't open.
        return err.error(
            err_id=("main", "test_package", "unopenable"),
            error="The package could not be opened.")
    except (BadZipfile, zlib_error):
        # Die if the zip file is corrupt.
        return err.error(
                err_id=("submain", "_load_install_rdf", "badzipfile"),
                error="Corrupt ZIP file",
                description="We were unable to decompress the zip file.")

    try:
        output = test_inner_package(err, package)
    except ValidationTimeout as ex:
        err.error(
                err_id=("main", "test_package", "timeout"),
                error="Validation timed out",
                description=["The validation process took too long to "
                             "complete. Contact an addons.mozilla.org editor "
                             "for more information.",
                             str(ex)])
        output = None

    return output


def test_inner_package(err, package):
    "Tests a package's inner content."

    # Iterate through each tier.
    for tier in sorted(decorator.get_tiers()):

        # Let the error bundler know what tier we're on.
        err.set_tier(tier)

        # Iterate through each test of our detected type.
        for test in decorator.get_tests(tier, err.detected_type):

            test_func = test["test"]
            if test["simple"]:
                test_func(err)
            else:
                # Pass in:
                # - Error Bundler
                # - A copy of the package itself
                test_func(err, package)

        # Return any errors at the end of the tier if undetermined.
        if err.failed(fail_on_warnings=False) and not err.determined:
            err.unfinished = True
            err.discard_unused_messages(ending_tier=tier)
            return err

    # Return the results.
    return err
