# moyaa
Moving dokku installations

##Usage
###Copy Authorized SSH-Keys
`fab source_host:user@my.server.com copy_authorized_keys:user@my-new.server.com`
###Create a backup
`fab source_host:user@my.server.com backup`
###Import backup
`fab destination:user@my-new.server.com import`
