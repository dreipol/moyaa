# moyaa
Moving dokku installations

##Usage
###Copy Authorized SSH-Keys
`fab source_host:user@my.server.com copy_authorized_keys:user@my-new.server.com`
###Create a backup
`fab source_host:user@my.server.com backup`
###Import backup
`fab destination:user@my-new.server.com import:dokku_backup_my.json`
There is also a dry run for the import script which just prints the methods:
`fab dest:user@my-new.server.com import:import:file=dokku_backup_my.json,dry_run=1`
