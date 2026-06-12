import os
import argparse
import xml.etree.ElementTree as ET

from enum import Enum
from curses.ascii import isdigit
from azure.devops.connection import Connection
from msrest.authentication import BasicAuthentication
from azure.devops.v5_1.test.models import RunCreateModel, ShallowReference, TestCaseResult, RunUpdateModel

# Helper Classes
class Status(Enum):
    PASSED = 'Passed'
    FAILED = 'Failed'
    COMPLETED = 'Completed'
    
    def __str__(self):
        return str(self.value)

class ExecutedTestCases:
    def __init__(self) -> None:
        self.failures = {}
        self.names = []
        
    def __str__(self) -> str:
        return str(self.__dict__)
    
class Configuration():
    personal_access_token = None
    organization_url = None
    project_name = None
    plan_id = None
    suite_id = None
    def __init__(self) -> None:
        self.personal_access_token = self.get_from_env("personal_access_token")
        self.organization_url = self.get_from_env("organization_url")
        self.project_name = self.get_from_env("project_name")
        try:
            self.plan_id = int(self.get_from_env("plan_id"))
        except ValueError:
            raise Exception("PLAN_ID must in an integer")
        try:
            self.suite_id = int(self.get_from_env("suite_id"))
        except ValueError:
            raise Exception("SUITE_ID must in an integer")
        
    def get_from_env(self, variable_name: str):
        variable_name = variable_name.upper()
        variable_value = os.getenv(variable_name)
        if not variable_value:
            raise Exception("Required environment variable {} not found".format(variable_name) )
        return variable_value
            
    
def update_result_test_point(outcome: str, point_id: int, result_points, error_message):
    point = next(filter(lambda point: point.test_point.id == str(point_id), result_points), None)
    if not point:
        raise Exception("Failed to find test points to update")
    point.outcome=outcome
    point.state = STATUS.COMPLETED
    point.error_message = error_message
    return point            
    
def get_connection():
    credentials = BasicAuthentication('', CONFIGURATION.personal_access_token)
    connection = Connection(base_url=CONFIGURATION.organization_url, creds=credentials)
    return connection

def main():
    project_name = CONFIGURATION.project_name
    plan_id = CONFIGURATION.plan_id
    suite_id = CONFIGURATION.suite_id
    
    connection = get_connection()
    test_client = connection.clients.get_test_client()
    points = test_client.get_points(project_name, plan_id, suite_id)


    tree = ET.parse(JUNIT_FILE)
    root = tree.getroot()

            
    executed_test_cases = ExecutedTestCases()

    for test_case in root:        
        test_case_name = test_case.attrib.get('name')
        if not test_case_name: continue
        executed_test_cases.names.append(test_case_name)
        
        for failure in test_case:
            # Ignore attributes that are not failures
            if failure.tag != "failure": continue
            executed_test_cases.failures[test_case_name] = failure.attrib.get('message')
            

    found_tests = list(filter(lambda point: point.test_case.name in executed_test_cases.names, points))

    if not found_tests:
        raise Exception(
            "No matching test points found in plan {} / suite {}.\n"
            "  Parsed from JUnit ({}): {}\n"
            "  Suite test case names ({}): {}".format(
                plan_id, suite_id,
                len(executed_test_cases.names), executed_test_cases.names,
                len(points), [point.test_case.name for point in points]))

    executed_points = []
    for found_test in found_tests:
        executed_points.append(found_test.id)

    test_run  = RunCreateModel()
    plan = ShallowReference(plan_id)
    test_run.automated = True
    test_run.name = "Virtuoso Execution Report"
    test_run.point_ids = executed_points
    test_run.plan = plan
    test_run = test_client.create_test_run(test_run, project_name)
    result_points = test_client.get_test_results(project_name, test_run.id)   
    app = []
    for found_test in found_tests:
        outcome = STATUS.PASSED
        error_message = ""
        failure = executed_test_cases.failures.get(found_test.test_case.name)
        if failure:
            outcome = STATUS.FAILED
            error_message = failure
        res = update_result_test_point(outcome, found_test.id, result_points, error_message)
        app.append(res)
    test_client.update_test_results(app, project_name, test_run.id)
    test_client.update_test_run(RunUpdateModel(state=STATUS.COMPLETED), project_name, test_run.id)
        
    
parser = argparse.ArgumentParser(description='Parse junit and update test case runs')

# Required positional argument
parser.add_argument('junit', type=str,
                    help='JUnit file location')
args = parser.parse_args()

# Get configuration variables from environment
CONFIGURATION = Configuration()
JUNIT_FILE = args.junit
STATUS = Status
#Execute main function
main()


