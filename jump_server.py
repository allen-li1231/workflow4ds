import time
import sys
import cx_Oracle
import paramiko
from threading import Thread

from .settings import (JUMP_SERVER_HOST, JUMP_SERVER_PORT, JUMP_SERVER_BACKEND_HOST,
                       JUMP_SERVER_PLSQL_HOST, JUMP_SERVER_PLSQL_SERVICE_NAME)


class SSH(paramiko.SSHClient):
    def __init__(self,
                 username, password,
                 jump_server_username, jump_server_password,
                 host=None, port=None,
                 file=sys.stdout):

        super().__init__()
        self.load_system_host_keys()
        self.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        self.connect(host or JUMP_SERVER_HOST, port or JUMP_SERVER_PORT,
                     username=jump_server_username, password=jump_server_password)
        self.shell = self.invoke_shell()
        # self.shell.set_combine_stderr(True)

        self.msg = ''
        self.file = file

        self.print_thread = Thread(target=self.print_forever, args=())
        self.print_thread.setDaemon(True)
        self.print_thread.start()

        self.execute(1)
        time.sleep(1)
        self.execute(1)
        self.execute(username)
        time.sleep(1)
        self.execute(password)

    def print_forever(self, wait=1):
        while True:
            msg = self.shell.recv(-1).decode()
            if len(msg.strip()) > 0:
                print(msg, file=self.file)
                self.msg = msg
            if "timed out waiting for input: auto-logout" in msg:
                return

            time.sleep(wait)

    def execute(self, command):
        self.shell.send(f"{command}\r")

    def close(self):
        self.print_thread.join()
        super().close()


class SFTP(paramiko.SFTPClient):
    def __init__(self,
                 username, password,
                 jump_server_username, jump_server_password,
                 host=None, port=None):
        t = paramiko.Transport(
            sock=(host or JUMP_SERVER_HOST, port or JUMP_SERVER_PORT)
        )
        t.connect(
            username=f"{jump_server_username}#{username}#{JUMP_SERVER_BACKEND_HOST}_sftp",
            password=f"{jump_server_password}#{password}"
        )
        chan = t.open_session()
        chan.invoke_subsystem("sftp")
        super().__init__(chan)


class Oracle:
    def __init__(self, username, password, service_name=None, hostname=None):
        """ Connect to the database. """
        self.hostname = hostname or JUMP_SERVER_PLSQL_HOST \
                        or ValueError("hostname not provided in argument or in settings")
        self.service_name = service_name or JUMP_SERVER_PLSQL_SERVICE_NAME \
                            or ValueError("service_name not provided in argument or in settings")
        try:
            self.db = cx_Oracle.connect(username, password,
                                        hostname + '/' + service_name)
            self.db.autocommit = True
        except cx_Oracle.DatabaseError as e:
            # Log error as appropriate
            raise
        # If the database connection succeeded create the cursor
        # we-re going to use.
        self.cursor = self.db.cursor()

    def close(self):
        """
        Disconnect from the database. If this fails, for instance
        if the connection instance doesn't exist, ignore the exception.
        """
        try:
            self.cursor.close()
            self.db.close()
        except cx_Oracle.DatabaseError:
            pass

    def execute(self, sql):
        """
        Execute whatever SQL statements are passed to the method;
        commit if specified. Do not specify fetchall() in here as
        the SQL statement may not be a select.
        """
        try:
            self.cursor.execute(sql)
        except cx_Oracle.DatabaseError as e:
            # Log error as appropriate
            raise

    def execute_proc(self, sql):
        """
        Execute whatever SQL procedure are passed to the method;
        commit if specified.
        """
        try:
            self.cursor.callproc(sql)
        except cx_Oracle.DatabaseError as e:
            # Log error as appropriate
            raise

    def fetchall(self):
        data = self.cursor.fetchall()
        col_names = []
        for i in range(0, len(self.cursor.description)):
            col_names.append(self.cursor.description[i][0])

        return {"data": data, "columns": col_names}