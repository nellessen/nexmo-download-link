#!/usr/bin/env python
# coding=UTF-8
# Title:       configuration.py
# Description: In this configuration file you can define additional message handler.
# Author       David Nellessen <david.nellessen@familo.net>
# Date:        12.01.15
# Note:        
# ==============================================================================

SIMPLE_MESSAGE_HANDLERS = {}

# Define simple message handlers. Syntax:
# SIMPLE_MESSAGE_HANDLERS['/desired_path/'] = {'message': 'The mssage that will be sent',
#                                              'sender': 'The sender title or phone number'}

# Example:
#SIMPLE_MESSAGE_HANDLERS['/example/'] = {'message': 'Lade hier Familonet https://www.familo.net/start',
#                                        'sender': 'Familonet'}