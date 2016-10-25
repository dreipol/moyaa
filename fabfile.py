from __future__ import print_function

import json
import os
import re

from fabric.api import run, env
from fabric.colors import red, green
from fabric.context_managers import settings
from fabric.contrib.files import exists
from fabric.decorators import task
from fabric.operations import prompt, sudo, put, get

ENVS_KEY = "envs"
DOMAINS_KEY = "domains"


class Host(object):
    def __init__(self, kind, address=None, user="ubuntu"):
        """

        :type kind: str
        """
        kind = kind.upper()
        if address:
            self.address = address
        else:
            self.address = os.environ.get("MOYAA_{kind}_SERVER".format(kind=kind))
        if user:
            self.user = user
        else:
            self.user = os.environ.get("MOYAA_{kind}_USER".format(kind=kind))
    
    def complete_address(self):
        return "{user}@{host}".format(user=self.user, host=self.address)
    
    def __unicode__(self):
        return self.complete_address()


dest_host = lambda: Host("DEST")
src_host = lambda: Host("SRC")


@task(alias="src")
def source_host(host_address=None, host=src_host()):
    """

    :type host: Host
    """
    
    if not host_address:
        host_address = host.complete_address()
    
    env.host_string = host_address
    env.forward_agent = True


@task(alias="dest")
def destination_host(host_address=None, host=dest_host()):
    if not host_address:
        host_address = host.complete_address()
    
    env.host_string = host_address
    env.forward_agent = True


@task(alias='cp_ssh')
def copy_authorized_keys(destination=dest_host().complete_address()):
    keys = "~/.ssh/authorized_keys"
    run("scp {keys} {server}:{keys}".format(keys=keys, server=destination))


@task
def create_ssh_login(destination=dest_host().complete_address()):
    print(destination)
    path = "~/.ssh/id_rsa"
    local_file = "id_rsa_{}.pub".format(get_current_host_name())
    pub_file = path + ".pub"
    if not exists(pub_file):
        run("ssh-keygen -t rsa -f {} -q -N \"\"".format(path))
    get(pub_file, local_file)
    
    with settings(host_string=destination):
        remote_filepath = "~/.ssh/{}".format(local_file)
        if not exists(remote_filepath):
            put(local_file, remote_filepath)
            run("cat {} >> ~/.ssh/authorized_keys".format(remote_filepath))
        run("cat {} | sudo sshcommand acl-add dokku {}".format(remote_filepath, get_current_host_name()))


def remote_app_path(app):
    return "/home/dokku/{}".format(app)


@task()
def get_nginx_files():
    all_apps = get_apps()
    for app in all_apps:
        path = remote_app_path(app) + "/nginx.conf.d/"
        if exists(path):
            get(path, "nginx_conf/{}".format(app))


@task()
def put_nginx_files():
    conf_dir = "nginx_conf"
    for app in os.listdir(conf_dir):
        local_path = "{}/{}/*".format(conf_dir, app)
        put(local_path, remote_app_path(app), use_sudo=True)


@task(alias='cp_nginx')
def copy_nginx_files(destination=dest_host().complete_address()):
    get_nginx_files()
    with settings(host_string=destination):
        put_nginx_files()


def backup_apps():
    print(green("Backup apps:"))
    all_apps = get_apps()
    apps_backup = dict()
    for app_name in all_apps:
        print("Backup {app}".format(app=app_name))
        dokku_result = dokku_run("domains", app_name, quiet=True)
        domains = dokku_result.rpartition("{app} Domain Names".format(app=app_name))
        app_domains = [d for d in domains[-1].splitlines() if d]
        
        conf_result = dokku_run("config", app_name, quiet=True)
        envs = conf_result.rpartition("config vars")[-1]
        envs = envs.splitlines()
        
        regex = re.compile(r"(:\s+)")
        config = [re.sub(regex, '=', e) for e in envs if e]
        
        apps_backup[app_name] = {DOMAINS_KEY: app_domains, ENVS_KEY: config}
    
    return apps_backup


def backup_plugins():
    print(green("Backup plugins"))
    response = dokku_run("plugin", quiet=True)
    plugins = response.splitlines()[1:]
    plugins_backup = {}
    for plugin in plugins:
        properties = plugin.split(None, 3)
        name = properties[0]
        version = properties[1]
        is_enabled = properties[2] == "enabled"
        plugins_backup[name] = {"version": version, "is_enabled": is_enabled}
    
    return plugins_backup


def get_apps():
    dokku_apps = dokku_run("apps", quiet=True)
    all_apps = dokku_apps.splitlines()[1:]
    return all_apps


@task(alias="backup")
def download_config():
    host_name = get_current_host_name()
    filename = "dokku_backup_{0}.json".format(host_name)
    should_overwrite = True
    if os.path.exists(filename):
        print(red("Backup file already exists locally:\n {}".format(filename)))
        message = "Should the file be overwritten? yes/no "
        should_overwrite = bool_prompt(message)
    if should_overwrite:
        content = {}
        content["host"] = env.host_string
        content["version"] = dokku_run("version", quiet=True)
        content["apps"] = backup_apps()
        content["plugins"] = backup_plugins()
        
        with open(filename, "w") as json_file:
            json.dump(content, json_file)
        
        print(green("\nBackup saved to: {}".format(filename)))
    else:
        print(red("backup has been cancelled"))


def get_current_host_name():
    regex = re.compile(ur"^(?:\w*@){0,1}(\w+).")
    host_name = re.search(regex, env.host_string).groups()[0]
    return host_name


def bool_prompt(message):
    prompt_response = prompt(message)
    return prompt_response.startswith('y')


def dokku_run(method, app_name=None, dokku_arg=None, is_debug=False, as_sudo=False, **kwargs):
    if is_debug:
        r = print
        kwargs = {}
    elif as_sudo:
        r = sudo
    else:
        r = run
    
    if not dokku_arg:
        dokku_arg = ""
    if not app_name:
        app_name = ""
    
    return r("dokku {method} {app} {arg}".format(method=method, app=app_name, arg=dokku_arg), **kwargs)


def import_plugins(plugins_dict, is_debug=False):
    installed_plugins = backup_plugins()
    print(red("The following plugins have to be installed MANUALLY:"))
    for name, properties in plugins_dict.iteritems():
        if not name in installed_plugins and properties["is_enabled"]:
            print(name)
            # dokku_run("plugin:install", name, as_sudo=True, is_debug=is_debug)
    return bool_prompt("\n\nI have installed the plugins manually. \nProceed?")


@task(alias="import")
def import_config(file, dry_run=False):
    if not os.path.exists(file):
        print(red("Cannot find file: {}".format(file)))
        return
    
    should_import = True
    
    if get_apps():
        print(red("This host already contains apps."))
        should_import = bool_prompt(red("Do you REALLY want to import the backup? yes/no"))
    
    if should_import:
        with open(file, "r") as json_file:
            config = json.load(json_file)
            should_proceed = import_plugins(config.get("plugins", {}), dry_run)
            if should_proceed:
                import_apps(config.get("apps", {}), dry_run)


def import_apps(config, is_debug):
    for name, settings in config.iteritems():
        dokku_run("apps:create", name, is_debug=is_debug)
        import_domains(is_debug, name, settings)
        import_envs(is_debug, name, settings)


def import_envs(is_debug, name, settings):
    envs = settings.get(ENVS_KEY, None)
    ignore_envs = {'DOKKU_DOCKERFILE_CMD'}
    if envs:
        env_str = " ".join([e for e in envs if e.split("=", 1)[0] not in ignore_envs])
        dokku_run("config:set", name, env_str, is_debug=is_debug)


def import_domains(is_debug, name, settings):
    for d in settings.get(DOMAINS_KEY, []):
        dokku_run("domains:add", name, d, is_debug=is_debug)
