from shutil import ExecError
import requests
from time import sleep
import json
from pprint import pprint as pp

from urllib3 import Retry

class VirtuosoApi(object):
    def __init__(self) -> None:
        self.api_token = ""
        self.api_url = "https://api.virtuoso.qa/api"
        self.ui_url = "https://app.virtuoso.qa"
        self.headers = {"X-Virtuoso-Client-Name:": "Robot Framework"}
        self.goal = self.Goal(self)
        self.journey = self.Journey(self)
        self.plan = self.Plan(self)
        self.project_id = 0
        self._request_delay = 5

    def _set_auth_header(self) -> None:
        self.headers = {"Authorization": "Bearer " + self.api_token}

    def set_virtuoso_environment(self, environment) -> None:
        self.set_api_url("https://api-{}.virtuoso.qa/api".format(environment))
        self.set_ui_url("https://app-{}.virtuoso.qa/api".format(environment))

    def set_project_id(self, project_id: int) -> None:
        self.project_id = project_id

    def set_api_url(self, api_url: str) -> None:
        self.api_url = api_url

    def set_ui_url(self, ui_url: str) -> None:
        self.ui_url = ui_url

    def set_api_token(self, api_token: str) -> None:
        self.api_token = api_token
        self._set_auth_header()

    def make_post_request(self, url: str, payload: object, retries: int = 0) -> json:
        full_url = self.api_url + url
        response = requests.post(full_url, headers=self.headers, json=payload)
        if response.status_code != 200:
            retries += 1
            # Retry 3 times if the status code is not 200
            if retries > 3:
                raise Exception("Failed api requests with status: {} - {}".format(response.status_code, response.__dict__))
            sleep(5)
            self.make_post_request(url, payload, retries)

        # Usually we should avoid catching all the exemptions  but in this case if converting the response to JSON
        # we want a pretty error regardless of the error type
        try:
            return response.json()
        except:
            raise Exception("Api response is not parsable {}".format(response.__dict__))

    def make_get_request(self, url: str, retries: int = 0) -> json:
        full_url = self.api_url + url
        response = requests.get(full_url, headers=self.headers)
        if response.status_code != 200:
            retries += 1
            # Retry 3 times if the status code is not 200
            if retries > 3:
                raise Exception("Failed api requests with status: {} - {}".format(response.status_code, response.__dict__))
            sleep(5)
            self.make_get_request(url, retries)

        # Usually we should avoid catching all the exemptions  but in this case if converting the response to JSON
        # we want a pretty error regardless of the error type
        try:
            return response.json()
        except:
            raise Exception("Api response is not parsable {}".format(response.__dict__))


    def check_execution_outcome(self, execution_id: int) -> str:
        finished_status = ["FINISHED", "CANCELED", "FAILED"]
        url = "/executions/{}/status?envelope=false".format(execution_id)
        execution = self.make_get_request(url)
        while not execution["status"] in finished_status:
            execution = self.make_get_request(url)
            sleep(self._request_delay)
        return execution["outcome"]

    class Goal(object):
        def __init__(self, virtuoso_api: str) -> None:
            self.api = virtuoso_api

        def get_latest_goal_snapshots(self, goal_id: int) -> int:
            goal_snapshots = self.api.make_get_request("/goals/{}/snapshots?envelope=false".format(goal_id))
            if len(goal_snapshots) < 1:
                raise Exception("Goal {} does not have any executed journeys".format(goal_id))
            return goal_snapshots[0]

        def get_goal_snapshot(self, goal_id, snapshot_id):
            snapshot = self.api.make_get_request(
                "/snapshots/{}/goals/{}/testsuites?envelope=false".format(snapshot_id, goal_id))
            if not snapshot:
                raise Exception("Could not get snapshot {} for goal {}".format(snapshot_id, goal_id))
            return snapshot


        def get_project_goals(self, project_id):
            project_goals = self.api.make_get_request(
                "/goals/?projectId={}&archived=false&envelope=false".format(project_id))
            return project_goals

        def execute_goal(self, goal_id):
            url = "/goals/{}/execute?envelope=false".format(goal_id)
            payload = {}
            execution = self.api.make_post_request(url, payload)
            return execution["id"]



    class Journey(object):
        def __init__(self, virtuoso_api) -> None:
            self.api = virtuoso_api

        # TODO: We should only get 1 journey or fail trying!!!
        def _get_journeys_to_execute(self, journey_names: list = None, goal_ids: list = None) -> object:

            journeys_to_execute = []
            # If no goal Id is given we transverse through all the project
            if not goal_ids:
                goal_ids = self.api.goal.getProjectGoals(self.api.project_id).keys()
            for goal_id in goal_ids:
                snapshot_id = self.api.goal.get_latest_goal_snapshots(goal_id)
                snapshot = self.api.goal.get_goal_snapshot(goal_id, snapshot_id)
                for journey in snapshot.values():
                    # This should break if we cannot find it
                    journey_id = journey["id"]
                    journey_title = journey["title"]
                    journey_data = {
                        "id": journey_id,
                        "title": journey_title,
                        "goalId": goal_id,
                        "projectId": self.api.project_id,
                        "snapshotId": snapshot_id
                    }
                    if journey_names:
                        if journey_title in journey_names:
                            journeys_to_execute.append(journey_data)
                    else:
                        journeys_to_execute.append(journey_data)
            return journeys_to_execute

        # TODO: We should only have 1 Journey to execute otherwise we would need to return a list of execution Ids
        def execute_journeys(self, journey_names: list = None, goal_ids: list = None):
            journeys_to_execute = self._get_journeys_to_execute(journey_names, goal_ids)
            for journey_to_execute in journeys_to_execute:
                payload = {
                    "tags": ["Automated"],
                    "suiteIds": [journey_to_execute["id"]]
                }
                url = "/goals/{}/snapshots/{}/execute?envelope=false".format(journey_to_execute["goalId"],
                                                                             journey_to_execute["snapshotId"])
                execution = self.api.make_post_request(url, payload)
                execution_id = execution.get("id")
                if not execution_id:
                    raise Exception("Execution with id {} not found".format(execution_id))
                return execution_id

    class Plan(object):
        def __init__(self, virtuoso_api) -> None:
            self.api = virtuoso_api
        def execute_plan(self, plan_id):
            url = "/plans/executions/{}/execute?envelope=false".format(plan_id)
            payload = {}
            execution = self.api.make_post_request(url, payload)
            # TODO: The plan has can have multiple jobs
            return next(iter(execution["jobs"].keys()))
