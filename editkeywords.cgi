#!/usr/bin/perl -wT
# -*- Mode: perl; indent-tabs-mode: nil -*-
#
# The contents of this file are subject to the Mozilla Public
# License Version 1.1 (the "License"); you may not use this file
# except in compliance with the License. You may obtain a copy of
# the License at http://www.mozilla.org/MPL/
#
# Software distributed under the License is distributed on an "AS
# IS" basis, WITHOUT WARRANTY OF ANY KIND, either express or
# implied. See the License for the specific language governing
# rights and limitations under the License.
#
# The Original Code is the Bugzilla Bug Tracking System.
#
# The Initial Developer of the Original Code is Terry Weissman.
# Portions created by Terry Weissman are
# Copyright (C) 2000 Terry Weissman. All
# Rights Reserved.
#
# Contributor(s): Terry Weissman <terry@mozilla.org>

use strict;
use lib ".";

require "globals.pl";

use Bugzilla;
use Bugzilla::Constants;
use Bugzilla::Config qw(:DEFAULT $datadir);
use Bugzilla::Token;

my $cgi = Bugzilla->cgi;
my $dbh = Bugzilla->dbh;
my $template = Bugzilla->template;
my $vars = {};

sub Validate {
    my ($name, $description) = @_;
    if ($name eq "") {
        ThrowUserError("keyword_blank_name");
    }
    if ($name =~ /[\s,]/) {
        ThrowUserError("keyword_invalid_name");
    }    
    if ($description eq "") {
        ThrowUserError("keyword_blank_description");
    }
    # It is safe to detaint these values as they are only
    # used in placeholders.
    trick_taint($name);
    $_[0] = $name;
    trick_taint($description);
    $_[1] = $description;
}

sub ValidateKeyID {
    my $id = shift;

    $id = trim($id || 0);
    detaint_natural($id) || ThrowCodeError('invalid_keyword_id');
    return $id;
}


#
# Preliminary checks:
#

my $user = Bugzilla->login(LOGIN_REQUIRED);

print $cgi->header();

$user->in_group('editkeywords')
  || ThrowUserError("auth_failure", {group  => "editkeywords",
                                     action => "edit",
                                     object => "keywords"});

my $action  = trim($cgi->param('action')  || '');
my $token   = $cgi->param('token');
$vars->{'action'} = $action;


if ($action eq "") {
    my @keywords;

    $vars->{'keywords'} =
      $dbh->selectall_arrayref('SELECT keyworddefs.id, keyworddefs.name,
                                       keyworddefs.description,
                                       COUNT(keywords.bug_id) AS bug_count
                                  FROM keyworddefs
                             LEFT JOIN keywords
                                    ON keyworddefs.id = keywords.keywordid ' .
                                  $dbh->sql_group_by('id', 'name, description') . '
                                 ORDER BY keyworddefs.name', {'Slice' => {}});

    print $cgi->header();
    $template->process("admin/keywords/list.html.tmpl", $vars)
      || ThrowTemplateError($template->error());

    exit;
}
    

if ($action eq 'add') {
    $vars->{'token'} = issue_session_token('add_keyword');
    print $cgi->header();

    $template->process("admin/keywords/create.html.tmpl", $vars)
      || ThrowTemplateError($template->error());

    exit;
}

#
# action='new' -> add keyword entered in the 'action=add' screen
#

if ($action eq 'new') {
    check_token_data($token, 'add_keyword');
    # Cleanups and validity checks

    my $name = trim($cgi->param('name') || '');
    my $description  = trim($cgi->param('description')  || '');

    Validate($name, $description);

    my $id = $dbh->selectrow_array('SELECT id FROM keyworddefs
                                    WHERE name = ?', undef, $name);

    if ($id) {
        $vars->{'name'} = $name;
        ThrowUserError("keyword_already_exists", $vars);
    }


    # Pick an unused number.  Be sure to recycle numbers that may have been
    # deleted in the past.  This code is potentially slow, but it happens
    # rarely enough, and there really aren't ever going to be that many
    # keywords anyway.

    my $existing_ids =
        $dbh->selectcol_arrayref('SELECT id FROM keyworddefs ORDER BY id');

    my $newid = 1;

    foreach my $oldid (@$existing_ids) {
        if ($oldid > $newid) {
            last;
        }
        $newid = $oldid + 1;
    }

    # Add the new keyword.
    $dbh->do('INSERT INTO keyworddefs
              (id, name, description) VALUES (?, ?, ?)',
              undef, ($newid, $name, $description));

    # Make versioncache flush
    unlink "$datadir/versioncache";
    delete_token($token);

    print $cgi->header();

    $vars->{'name'} = $name;
    $template->process("admin/keywords/created.html.tmpl", $vars)
      || ThrowTemplateError($template->error());

    exit;
}

    

#
# action='edit' -> present the edit keywords from
#
# (next action would be 'update')
#

if ($action eq 'edit') {
    my $id = ValidateKeyID(scalar $cgi->param('id'));

    # get data of keyword
    my ($name, $description) =
        $dbh->selectrow_array('SELECT name, description FROM keyworddefs
                               WHERE id = ?', undef, $id);

    if (!$name) {
        $vars->{'id'} = $id;
        ThrowCodeError("invalid_keyword_id", $vars);
    }

    my $bugs = $dbh->selectrow_array('SELECT COUNT(*) FROM keywords
                                      WHERE keywordid = ?',
                                      undef, $id);

    $vars->{'keyword_id'} = $id;
    $vars->{'name'} = $name;
    $vars->{'description'} = $description;
    $vars->{'bug_count'} = $bugs;
    $vars->{'token'} = issue_session_token('edit_keyword');

    print $cgi->header();

    $template->process("admin/keywords/edit.html.tmpl", $vars)
      || ThrowTemplateError($template->error());

    exit;
}


#
# action='update' -> update the keyword
#

if ($action eq 'update') {
    check_token_data($token, 'edit_keyword');
    my $id = ValidateKeyID(scalar $cgi->param('id'));

    my $name  = trim($cgi->param('name') || '');
    my $description  = trim($cgi->param('description')  || '');

    Validate($name, $description);

    my $tmp = $dbh->selectrow_array('SELECT id FROM keyworddefs
                                     WHERE name = ?', undef, $name);

    if ($tmp && $tmp != $id) {
        $vars->{'name'} = $name;
        ThrowUserError("keyword_already_exists", $vars);
    }

    $dbh->do('UPDATE keyworddefs SET name = ?, description = ?
              WHERE id = ?', undef, ($name, $description, $id));

    # Make versioncache flush
    unlink "$datadir/versioncache";
    delete_token($token);

    print $cgi->header();

    $vars->{'name'} = $name;
    $template->process("admin/keywords/rebuild-cache.html.tmpl", $vars)
      || ThrowTemplateError($template->error());

    exit;
}


if ($action eq 'del') {
    my $id = ValidateKeyID(scalar $cgi->param('id'));

    my $name = $dbh->selectrow_array('SELECT name FROM keyworddefs
                                      WHERE id= ?', undef, $id);

    my $bugs = $dbh->selectrow_array('SELECT COUNT(*) FROM keywords
                                      WHERE keywordid = ?',
                                      undef, $id);

    $vars->{'bug_count'} = $bugs;
    $vars->{'keyword_id'} = $id;
    $vars->{'name'} = $name;
    $vars->{'token'} = issue_session_token('delete_keyword');

    print $cgi->header();

    $template->process("admin/keywords/confirm-delete.html.tmpl", $vars)
      || ThrowTemplateError($template->error());
    exit;
}

if ($action eq 'delete') {
    check_token_data($token, 'delete_keyword');
    my $id = ValidateKeyID(scalar $cgi->param('id'));

    my $name = $dbh->selectrow_array('SELECT name FROM keyworddefs
                                      WHERE id= ?', undef, $id);

    $dbh->do('DELETE FROM keywords WHERE keywordid = ?', undef, $id);
    $dbh->do('DELETE FROM keyworddefs WHERE id = ?', undef, $id);

    # Make versioncache flush
    unlink "$datadir/versioncache";
    delete_token($token);

    print $cgi->header();

    $vars->{'name'} = $name;
    $template->process("admin/keywords/rebuild-cache.html.tmpl", $vars)
      || ThrowTemplateError($template->error());

    exit;
}

ThrowCodeError("action_unrecognized", $vars);
