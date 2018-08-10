#!/usr/bin/env python3
"""Author:      Olivier van der Toorn <oliviervdtoorn@gmail.com>
Description:    Bridges GOGS with Matrix"""
import logging
import hashlib
import hmac
import yaml
import sys
from flask import Flask, request

import matrix

app = Flask(__name__)
issue_filter = ['created', 'label_updated']


def send_message(room, message):
    config = matrix.read_config('/etc/matrix.conf')
    config['message'] = message # .replace('\n', '<br />')
    config['room'] = room
    client, room = matrix.setup(config)
    matrix.send_message(config, room)


def commit(data):
    """Parses commit messages from the webhook.

    :param data: json input data
    :type data: dict
    :return: list of messages
    """
    messages = []
    ref = data['ref']
    for commit in data['commits']:
        commit_id = commit['id']
        date = commit['timestamp']
        author = commit['author']['name']
        committer = commit['committer']['name']
        message = commit['message']
        return_message = (
            'commit {commit_id} onto {ref}\n'
            'Author: {author} ({committer})\n'
            'Date: {date}\n\n'
            '{message}').format(
                ref=ref,
                commit_id=commit_id,
                author=author,
                committer=committer,
                date=date,
                message=message,
            )
        messages.append(return_message)

    return messages


def pull_request(data):
    """Handles pull request events.

    :param data: input json data
    :type data: dict
    :return: list of messages
    """
    messages = []
    number = data['number']
    action = data['action']
    user = data['sender']['full_name']
    title = data['pull_request']['title']
    body = data['pull_request']['body']
    head_branch = data['pull_request']['head_branch']
    base_branch = data['pull_request']['base_branch']
    url = data['pull_request']['html_url']
    mergeable = str(data['pull_request']['mergeable'])
    if action == 'opened' or action == 'reopened':
        message = (
            '{user} wants to merge "{head_branch}" into "{base_branch}" '
            '(mergeable: {mergeable})\n'
            'URL: {url}\n\n'
            '{title}\n'
            '{body}'
        ).format(
            user=user,
            head_branch=head_branch,
            base_branch=base_branch,
            mergeable=mergeable,
            url=url,
            title=title,
            body=body
        )

    elif action == 'synchronized':
        message = (
            '{user} updated pull-request "#{number}"'
        ).format(
            user=user,
            number=number
        )

    elif action == 'closed':
        message = (
            '{user} closed pull-request "#{number}"'
        ).format(
            user=user,
            number=number)

    else:
        message = action

    messages.append(message)
    return messages


def comment(data):
    """Handles comment events.

    :param data: the json webhook data
    :return: messages
    """
    messages = []
    action = data['action']
    url = data['comment']['html_url']
    user = data['sender']['full_name']
    body = data['comment']['body']
    if action == 'deleted':
        message = (
            '{user} {action} a comment\n'
            'URL: {url}\n'
        ).format(
            user=user,
            action=action,
            url=url
        )

    else:
        message = (
            '{user} {action} a comment\n'
            'URL: {url}\n\n'
            '{body}\n'
        ).format(
            user=user,
            action=action,
            url=url,
            body=body
        )

    messages.append(message)
    return messages


def issue(data):
    """Handles issue events.

    :param data: the json webhook data
    :return: messages
    """
    messages = []
    action = data['action']
    html_url = data['repository']['html_url']
    title = data['issue']['title']
    body = data['issue']['body']
    user = data['sender']['full_name']
    issue_id = data['issue']['number']
    full_url = '{0}/issues/{1}'.format(html_url, issue_id)

    if action == 'label_cleared':
        action = 'cleared the labels of'

    elif action == 'label_updated':
        action = 'updated the labels of'

    if action == 'opened':
        message = (
            '{user} {action} an issue\n'
            'URL: {full_url}\n\n'
            '{title}\n'
            '{body}\n'
        ).format(
            user=user,
            action=action,
            full_url=full_url,
            title=title,
            body=body
        )

    else:
        message = (
            '{user} {action} an issue\n'
            'URL: {full_url}\n'
        ).format(
            user=user,
            action=action,
            full_url=full_url,
        )

    messages.append(message)
    return messages


@app.route('/', defaults={'path': ''}, methods=['POST'])
@app.route('/<path:path>', methods=['POST'])
def git(path):
    messages = []
    if request.method == 'POST':
        signature = request.headers.get('X-Gogs-Signature')
        hash_secret = hmac.new(
            bytes(CONFIG['secret'], 'utf-8'), msg=request.data,
            digestmod=hashlib.sha256).hexdigest()
        if signature == hash_secret:
            json_data = request.get_json()
            logging.debug("incoming data: %s", json_data)
            if 'commits' in json_data.keys():
                messages.extend(commit(json_data))

            if 'pull_request' in json_data.keys():
                messages.extend(pull_request(json_data))

            if 'comment' in json_data.keys():
                messages.extend(comment(json_data))

            if ('issue' in json_data.keys()
                    and 'comment' not in json_data.keys()):
                messages.extend(issue(json_data))

    return_message = "\n\n".join(messages)
    logging.debug(return_message)
    send_message(CONFIG['channels'][path], return_message)
    return return_message


if __name__ == '__main__':
    FORMAT = '%(asctime)-15s %(funcName)-15s: %(message)s'
    logging.basicConfig(format=FORMAT, level='DEBUG')
    with open('config.yaml', 'r') as yaml_file:
        CONFIG = yaml.load(yaml_file)

    app.run(host='0.0.0.0')
