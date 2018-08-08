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


def send_message(room, message):
    config = matrix.read_config('/etc/matrix.conf')
    config['message'] = message.replace('\n', '<br />')
    config['room'] = room
    client, room = matrix.setup(config)
    matrix.send_message(config, room)


def commit(commit_data):
    messages = []
    for commit in commit_data:
        commit_id = commit['id']
        date = commit['timestamp']
        url = commit['url']
        author = commit['author']['name']
        committer = commit['committer']['name']
        message = commit['message']
        return_message = (
            'commit {commit_id}\n'
            'URL: {url}\n'
            'Author: {author} ({committer})\n'
            'Date: {date}\n\n'
            '{message}').format(
                commit_id=commit_id,
                url=url,
                author=author,
                committer=committer,
                date=date,
                message=message,
            )
        messages.append(return_message)

    return messages


def pull_request(number, action, pull_data):
    messages = []
    user = pull_data['user']['full_name']
    title = pull_data['title']
    body = pull_data['body']
    head_branch = pull_data['head_branch']
    base_branch = pull_data['base_branch']
    url = pull_data['html_url']
    mergeable = str(pull_data['mergeable'])
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


def comment(action, comment_data):
    messages = []
    url = comment_data['html_url']
    user = comment_data['user']['full_name']
    body = comment_data['body']
    message = (
        '{user} {action} a comment\n'
        'URL: {url}\n\n'
        '{body}'
    ).format(
        user=user,
        action=action,
        url=url,
        body=body
    )
    messages.append(message)
    return messages


def issue(html_url, action, issue_data):
    messages = []
    title = issue_data['title']
    body = issue_data['body']
    user = issue_data['user']['full_name']
    issue_id = issue_data['number']
    full_url = '{0}/issues/{1}'.format(html_url, issue_id)
    message = (
        '{user} {action} an issue\n'
        'URL: {full_url}\n\n'
        '{title}\n'
        '{body}'
    ).format(
        user=user,
        action=action,
        full_url=full_url,
        title=title,
        body=body
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
                commit_data = json_data['commits']
                messages.extend(commit(commit_data))

            if 'pull_request' in json_data.keys():
                number = json_data['number']
                action = json_data['action']
                pull_data = json_data['pull_request']
                messages.extend(pull_request(number, action, pull_data))

            if 'comment' in json_data.keys():
                action = json_data['action']
                comment_data = json_data['comment']
                messages.extend(comment(action, comment_data))

            if ('issue' in json_data.keys()
                    and json_data['action'] != 'label_updated'):
                html_url = json_data['repository']['html_url']
                action = json_data['action']
                issue_data = json_data['issue']
                messages.extend(issue(html_url, action, issue_data))

    return_message = "\n\n".join(messages)
    logging.debug(return_message)
    send_message(CONFIG['channels'][path], return_message)
    return return_message


if __name__ == '__main__':
    FORMAT = '%(asctime)-15s %(funcName)-15s: %(message)s'
    logging.basicConfig(format=FORMAT, level='DEBUG')
    with open('config.yaml', 'r') as yaml_file:
        import pdb; pdb.set_trace() # BREAKPOINT
        CONFIG = yaml.load(yaml_file)

    app.run(host='0.0.0.0')
