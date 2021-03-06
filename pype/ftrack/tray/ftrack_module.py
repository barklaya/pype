import os
import time
import datetime
import threading
from Qt import QtCore, QtWidgets

import ftrack_api
from ..ftrack_server.lib import check_ftrack_url
from ..ftrack_server import socket_thread
from ..lib import credentials
from . import login_dialog

from pypeapp import Logger


log = Logger().get_logger("FtrackModule", "ftrack")


class FtrackModule:
    def __init__(self, main_parent=None, parent=None):
        self.parent = parent
        self.widget_login = login_dialog.Login_Dialog_ui(self)
        self.thread_action_server = None
        self.thread_socket_server = None
        self.thread_timer = None

        self.bool_logged = False
        self.bool_action_server_running = False
        self.bool_action_thread_running = False
        self.bool_timer_event = False

    def show_login_widget(self):
        self.widget_login.show()

    def validate(self):
        validation = False
        cred = credentials.get_credentials()
        ft_user = cred.get("username")
        ft_api_key = cred.get("api_key")
        validation = credentials.check_credentials(ft_user, ft_api_key)
        if validation:
            credentials.set_env(ft_user, ft_api_key)
            log.info("Connected to Ftrack successfully")
            self.loginChange()

            return validation

        if not validation and ft_user and ft_api_key:
            log.warning(
                "Current Ftrack credentials are not valid. {}: {} - {}".format(
                    str(os.environ.get("FTRACK_SERVER")), ft_user, ft_api_key
                )
            )

        log.info("Please sign in to Ftrack")
        self.bool_logged = False
        self.show_login_widget()
        self.set_menu_visibility()

        return validation

    # Necessary - login_dialog works with this method after logging in
    def loginChange(self):
        self.bool_logged = True
        self.set_menu_visibility()
        self.start_action_server()

    def logout(self):
        credentials.clear_credentials()
        self.stop_action_server()

        log.info("Logged out of Ftrack")
        self.bool_logged = False
        self.set_menu_visibility()

    # Actions part
    def start_action_server(self):
        if self.thread_action_server is None:
            self.thread_action_server = threading.Thread(
                target=self.set_action_server
            )
            self.thread_action_server.start()

    def set_action_server(self):
        if self.bool_action_server_running:
            return

        self.bool_action_server_running = True
        self.bool_action_thread_running = False

        ftrack_url = os.environ['FTRACK_SERVER']

        parent_file_path = os.path.dirname(
            os.path.dirname(os.path.realpath(__file__))
        )

        min_fail_seconds = 5
        max_fail_count = 3
        wait_time_after_max_fail = 10

        # Threads data
        thread_name = "ActionServerThread"
        thread_port = 10021
        subprocess_path = (
            "{}/ftrack_server/sub_user_server.py".format(parent_file_path)
        )
        if self.thread_socket_server is not None:
            self.thread_socket_server.stop()
            self.thread_socket_server.join()
            self.thread_socket_server = None

        last_failed = datetime.datetime.now()
        failed_count = 0

        ftrack_accessible = False
        printed_ftrack_error = False

        # Main loop
        while True:
            if not self.bool_action_server_running:
                log.debug("Action server was pushed to stop.")
                break

            # Check if accessible Ftrack and Mongo url
            if not ftrack_accessible:
                ftrack_accessible = check_ftrack_url(ftrack_url)

            # Run threads only if Ftrack is accessible
            if not ftrack_accessible:
                if not printed_ftrack_error:
                    log.warning("Can't access Ftrack {}".format(ftrack_url))

                if self.thread_socket_server is not None:
                    self.thread_socket_server.stop()
                    self.thread_socket_server.join()
                    self.thread_socket_server = None
                    self.bool_action_thread_running = False
                    self.set_menu_visibility()

                printed_ftrack_error = True

                time.sleep(1)
                continue

            printed_ftrack_error = False

            # Run backup thread which does not requeire mongo to work
            if self.thread_socket_server is None:
                if failed_count < max_fail_count:
                    self.thread_socket_server = socket_thread.SocketThread(
                        thread_name, thread_port, subprocess_path
                    )
                    self.thread_socket_server.start()
                    self.bool_action_thread_running = True
                    self.set_menu_visibility()

                elif failed_count == max_fail_count:
                    log.warning((
                        "Action server failed {} times."
                        " I'll try to run again {}s later"
                    ).format(
                        str(max_fail_count), str(wait_time_after_max_fail))
                    )
                    failed_count += 1

                elif ((
                    datetime.datetime.now() - last_failed
                ).seconds > wait_time_after_max_fail):
                    failed_count = 0

            # If thread failed test Ftrack and Mongo connection
            elif not self.thread_socket_server.isAlive():
                self.thread_socket_server.join()
                self.thread_socket_server = None
                ftrack_accessible = False

                self.bool_action_thread_running = False
                self.set_menu_visibility()

                _last_failed = datetime.datetime.now()
                delta_time = (_last_failed - last_failed).seconds
                if delta_time < min_fail_seconds:
                    failed_count += 1
                else:
                    failed_count = 0
                last_failed = _last_failed

            time.sleep(1)

        self.bool_action_thread_running = False
        self.bool_action_server_running = False
        self.set_menu_visibility()

    def reset_action_server(self):
        self.stop_action_server()
        self.start_action_server()

    def stop_action_server(self):
        try:
            self.bool_action_server_running = False
            if self.thread_socket_server is not None:
                self.thread_socket_server.stop()
                self.thread_socket_server.join()
                self.thread_socket_server = None

            if self.thread_action_server is not None:
                self.thread_action_server.join()
                self.thread_action_server = None

            log.info("Ftrack action server was forced to stop")

        except Exception:
            log.warning(
                "Error has happened during Killing action server",
                exc_info=True
            )

    # Definition of Tray menu
    def tray_menu(self, parent_menu):
        # Menu for Tray App
        self.menu = QtWidgets.QMenu('Ftrack', parent_menu)
        self.menu.setProperty('submenu', 'on')

        # Actions - server
        self.smActionS = self.menu.addMenu("Action server")

        self.aRunActionS = QtWidgets.QAction(
            "Run action server", self.smActionS
        )
        self.aResetActionS = QtWidgets.QAction(
            "Reset action server", self.smActionS
        )
        self.aStopActionS = QtWidgets.QAction(
            "Stop action server", self.smActionS
        )

        self.aRunActionS.triggered.connect(self.start_action_server)
        self.aResetActionS.triggered.connect(self.reset_action_server)
        self.aStopActionS.triggered.connect(self.stop_action_server)

        self.smActionS.addAction(self.aRunActionS)
        self.smActionS.addAction(self.aResetActionS)
        self.smActionS.addAction(self.aStopActionS)

        # Actions - basic
        self.aLogin = QtWidgets.QAction("Login", self.menu)
        self.aLogin.triggered.connect(self.validate)
        self.aLogout = QtWidgets.QAction("Logout", self.menu)
        self.aLogout.triggered.connect(self.logout)

        self.menu.addAction(self.aLogin)
        self.menu.addAction(self.aLogout)

        self.bool_logged = False
        self.set_menu_visibility()

        parent_menu.addMenu(self.menu)

    def tray_start(self):
        self.validate()

    def tray_exit(self):
        self.stop_action_server()

    # Definition of visibility of each menu actions
    def set_menu_visibility(self):

        self.smActionS.menuAction().setVisible(self.bool_logged)
        self.aLogin.setVisible(not self.bool_logged)
        self.aLogout.setVisible(self.bool_logged)

        if self.bool_logged is False:
            if self.bool_timer_event is True:
                self.stop_timer_thread()
            return

        self.aRunActionS.setVisible(not self.bool_action_server_running)
        self.aResetActionS.setVisible(self.bool_action_thread_running)
        self.aStopActionS.setVisible(self.bool_action_server_running)

        if self.bool_timer_event is False:
            self.start_timer_thread()

    def start_timer_thread(self):
        try:
            if self.thread_timer is None:
                self.thread_timer = FtrackEventsThread(self)
                self.bool_timer_event = True
                self.thread_timer.signal_timer_started.connect(
                    self.timer_started
                )
                self.thread_timer.signal_timer_stopped.connect(
                    self.timer_stopped
                )
                self.thread_timer.start()
        except Exception:
            pass

    def stop_timer_thread(self):
        try:
            if self.thread_timer is not None:
                self.thread_timer.terminate()
                self.thread_timer.wait()
                self.thread_timer = None

        except Exception as e:
            log.error("During Killing Timer event server: {0}".format(e))

    def changed_user(self):
        self.stop_action_server()
        credentials.set_env()
        self.validate()

    def process_modules(self, modules):
        if 'TimersManager' in modules:
            self.timer_manager = modules['TimersManager']
            self.timer_manager.add_module(self)

        if "UserModule" in modules:
            credentials.USER_GETTER = modules["UserModule"].get_user
            modules["UserModule"].register_callback_on_user_change(
                self.changed_user
            )


    def start_timer_manager(self, data):
        if self.thread_timer is not None:
            self.thread_timer.ftrack_start_timer(data)

    def stop_timer_manager(self):
        if self.thread_timer is not None:
            self.thread_timer.ftrack_stop_timer()

    def timer_started(self, data):
        if hasattr(self, 'timer_manager'):
            self.timer_manager.start_timers(data)

    def timer_stopped(self):
        if hasattr(self, 'timer_manager'):
            self.timer_manager.stop_timers()


class FtrackEventsThread(QtCore.QThread):
    # Senders
    signal_timer_started = QtCore.Signal(object)
    signal_timer_stopped = QtCore.Signal()

    def __init__(self, parent):
        super(FtrackEventsThread, self).__init__()
        cred = credentials.get_credentials()
        self.username = cred['username']
        self.user = None
        self.last_task = None

    def run(self):
        self.timer_session = ftrack_api.Session(auto_connect_event_hub=True)
        self.timer_session.event_hub.subscribe(
            'topic=ftrack.update and source.user.username={}'.format(
                self.username
            ),
            self.event_handler)

        user_query = 'User where username is "{}"'.format(self.username)
        self.user = self.timer_session.query(user_query).one()

        timer_query = 'Timer where user.username is "{}"'.format(self.username)
        timer = self.timer_session.query(timer_query).first()
        if timer is not None:
            self.last_task = timer['context']
            self.signal_timer_started.emit(
                self.get_data_from_task(self.last_task)
            )

        self.timer_session.event_hub.wait()

    def get_data_from_task(self, task_entity):
        data = {}
        data['task_name'] = task_entity['name']
        data['task_type'] = task_entity['type']['name']
        data['project_name'] = task_entity['project']['full_name']
        data['hierarchy'] = self.get_parents(task_entity['parent'])

        return data

    def get_parents(self, entity):
        output = []
        if entity.entity_type.lower() == 'project':
            return output
        output.extend(self.get_parents(entity['parent']))
        output.append(entity['name'])

        return output

    def event_handler(self, event):
        try:
            if event['data']['entities'][0]['objectTypeId'] != 'timer':
                return
        except Exception:
            return

        new = event['data']['entities'][0]['changes']['start']['new']
        old = event['data']['entities'][0]['changes']['start']['old']

        if old is None and new is None:
            return

        timer_query = 'Timer where user.username is "{}"'.format(self.username)
        timer = self.timer_session.query(timer_query).first()
        if timer is not None:
            self.last_task = timer['context']

        if old is None:
            self.signal_timer_started.emit(
                self.get_data_from_task(self.last_task)
            )
        elif new is None:
            self.signal_timer_stopped.emit()

    def ftrack_stop_timer(self):
        actual_timer = self.timer_session.query(
            'Timer where user_id = "{0}"'.format(self.user['id'])
        ).first()

        if actual_timer is not None:
            self.user.stop_timer()
            self.timer_session.commit()
            self.signal_timer_stopped.emit()

    def ftrack_start_timer(self, input_data):
        if self.user is None:
            return

        actual_timer = self.timer_session.query(
            'Timer where user_id = "{0}"'.format(self.user['id'])
        ).first()
        if (
            actual_timer is not None and
            input_data['task_name'] == self.last_task['name'] and
            input_data['hierarchy'][-1] == self.last_task['parent']['name']
        ):
            return

        input_data['entity_name'] = input_data['hierarchy'][-1]

        task_query = (
            'Task where name is "{task_name}"'
            ' and parent.name is "{entity_name}"'
            ' and project.full_name is "{project_name}"'
        ).format(**input_data)

        task = self.timer_session.query(task_query).one()
        self.last_task = task
        self.user.start_timer(task)
        self.timer_session.commit()
        self.signal_timer_started.emit(
            self.get_data_from_task(self.last_task)
        )
