from __future__ import print_function

import json
import os
import re

from fabric.api import run, env
from fabric.colors import red, green
from fabric.decorators import task
from fabric.operations import prompt, sudo


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


@task(alias='cp_ssh')
def copy_authorized_keys(destination=dest_host().complete_address()):
    keys = "~/.ssh/authorized_keys"
    run("scp {keys} {server}:{keys}".format(keys=keys, server=destination))


def backup_apps():
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
        config = " ".join([re.sub(regex, '=', e) for e in envs if e])
        
        apps_backup[app_name] = {"domains": app_domains, "conf": config}
    
    return apps_backup


def backup_plugins():
    response = dokku_run("plugin")
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
    regex = re.compile(ur"^(?:\w*@){0,1}(\w+).")
    host_name = re.search(regex, env.host_string).groups()[0]
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
        for d in settings.get("domains", []):
            dokku_run("domains:add", name, d, is_debug=is_debug)
        
        conf = settings.get("conf", None)
        if conf:
            dokku_run("config:set", name, conf, is_debug=is_debug)
