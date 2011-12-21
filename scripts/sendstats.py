#!/usr/bin/python
# Email a summary report of the bug statistics which also embeds the PNG chart
# generated by teamgraph.py
import sys, os, smtplib, time, MySQLdb, operator
from datetime import date, timedelta
from time import strftime
from string import join, split
from email.MIMEMultipart import MIMEMultipart
from email.MIMEText import MIMEText
from email.MIMEImage import MIMEImage
from settings import *

# extra debug output
if "--debug" in sys.argv: DEBUG = True
else: DEBUG = False

# set up database connection
try:
    db = MySQLdb.connect(host=DB_HOST, user=DB_USER, passwd=DB_PASS, db=DB_NAME)
    c = db.cursor(MySQLdb.cursors.DictCursor)
except:
    print "sendstats.py: can't connect to database\n"
    sys.exit()

# return the most recent date from our data set
def getThisWeekDate(slashed=False):
    sql = "select distinct date from Details order by date desc limit 1;"
    c.execute(sql)
    row = c.fetchone()
    if slashed:
        return row["date"].strftime("%m/%d/%y")
    else:
        return row["date"].strftime("%Y-%m-%d")

# return the second-most recent date from our data set
def getLastWeekDate(slashed=False):
    sql = "select distinct date from Details order by date desc limit 1,1;"
    c.execute(sql)
    row = c.fetchone()
    if slashed:
        return row["date"].strftime("%m/%d/%y")
    else:
        return row["date"].strftime("%Y-%m-%d")

# format a number so positive values have a leading "+"
def getDelta(n):
    if n > 0:
        return "+" + str(n)
    else:
        return n

# given two lists of bug numbers, return the set that went away in the latter
def getCleared(curBugs, lastBugs):
    cur = split(curBugs, ",")
    last = split(lastBugs, ",")
    cleared = []
    for bug in last:
        if len(bug) and bug not in cur: cleared.append(bug)
    return cleared

# given two lists of bug numbers, return the set that showed up in the latter
def getAdded(curBugs, lastBugs):
    cur = split(curBugs, ",")
    last = split(lastBugs, ",")
    added = []
    for bug in cur:
        if len(bug) and bug not in last: added.append(bug)
    return added

# simple object to store and sort data from multiple queries
class DataRow():
    def __init__(self):
        self.numCritical = 0
        self.critList = ""
        self.numHigh = 0
        self.highList = ""
        self.numModerate = 0
        self.modList = ""
        self.numLow = 0
        self.lowList = ""
        self.total = 0
        self.product = ""
        self.component = ""
    def dump(self):
        s = "Critical: "+str(self.numCritical)+", "
        s += "High: "+str(self.numHigh)+", "
        s += "Moderate: "+str(self.numModerate)+", "
        s += "Low: "+str(self.numLow)+", "
        return s

# start building email body
body = "<html>\n<body>\n<head>\n<style type=\"text/css\">.number{text-align:center;}table{margin:0 1em;border:1px solid black;border-collapse:collapse}th{text-align:left;padding:0 .5em}td{padding:0 .5em;border-top:1px solid #000;padding-top:.2em}td.total{border-top:3px double #000}th.header{font-weight:600}th.bright,td.bright{border-right:1px solid #000;font-weight:bold}.small{font-size:70%}.medium{font-size:80%}.gray{background-color:#eee}</style>\n</head>\n"
body += "<body>\n<p>Hello,</p><p>Here are some statistics regarding Mozilla Security Bugs for the week of %s:</p>\n<h2>Open Bugs By Severity</h2>\n<table>\n<tr><th>Category</th><th>Current</th><th>Last</th><th>Delta</th></tr>\n" % (getThisWeekDate(True))

# keep track of totals for counts
curTotal = 0
lastTotal = 0
totCleared = []
totAdded = []
i = 0

# bug counts
for cat in [("sg_critical", "Critical"), ("sg_high", "High"), ("sg_moderate", "Moderate"), ("sg_low", "Low")]:
    # get the stats from this week
    sql = "select d.count, d.bug_list from Details d, Stats s where d.sid=s.sid and s.category='%s' and d.date like '%s%%';" % (cat[0], getThisWeekDate())
    c.execute(sql)
    thisWkCount = 0
    thisWkList = ""
    row = c.fetchone()
    while row != None:
        thisWkCount += row["count"]
        thisWkList += row["bug_list"] if not len(thisWkList) else ","+row["bug_list"]
        row = c.fetchone()
    # get the stats from last week
    sql = "select d.count, d.bug_list from Details d, Stats s where d.sid=s.sid and s.category='%s' and d.date like '%s%%';" % (cat[0], getLastWeekDate())
    c.execute(sql)
    lastWkCount = 0
    lastWkList = ""
    row = c.fetchone()
    while row != None:
        lastWkCount += row["count"]
        lastWkList += row["bug_list"] if not len(lastWkList) else ","+row["bug_list"]
        row = c.fetchone()
    # find out which bugs were cleared and which were added in the past week
    cleared = getCleared(thisWkList, lastWkList)
    added = getAdded(thisWkList, lastWkList)
    if i%2 == 0: body += "<tr class=\"gray\">\n"
    else: body += "<tr>\n"
    # current count
    if thisWkCount > 0:
        curLink = "<a href=\"https://bugzilla.mozilla.org/buglist.cgi?bug_id=%s\">%s</a>" % (thisWkList, thisWkCount)
    else: curLink = "0"
    # previous count
    if lastWkCount > 0:
        prevLink = "<a href=\"https://bugzilla.mozilla.org/buglist.cgi?bug_id=%s\">%s</a>" % (lastWkList, lastWkCount)
    else: prevLink = "0"
    body += "  <td>%s</td>\n  <td class=\"number\">%s</td>\n  <td class=\"number\">%s</td>\n  <td class=\"number\">%s</td>\n  <td class=\"small\">" % (cat[1], curLink, prevLink, getDelta(thisWkCount-lastWkCount))
    # links to lists of cleared and added bugs
    if len(cleared) > 0:
        body += "(<a href=\"https://bugzilla.mozilla.org/buglist.cgi?bug_id=%s\">Cleared %s</a>, " % (join(cleared,","), len(cleared))
    else: body += "(Cleared 0, "
    if len(added) > 0:
        body += "<a href=\"https://bugzilla.mozilla.org/buglist.cgi?bug_id=%s\">Added %s</a>)</td>\n</tr>\n" % (join(added,","), len(added))
    else: body += "Added 0)</td>\n</tr>\n"
    curTotal += thisWkCount
    lastTotal += lastWkCount
    totCleared += cleared
    totAdded += added
    i += 1 # alternate row color

body += "<tr class=\"gray\">\n  <td class=\"total\">&nbsp;</td>\n  <td class=\"number total\">%s</td>\n  <td class=\"number total\">%s</td>\n  <td class=\"number total\">%s</td>\n  <td class=\"total small\">" % (curTotal, lastTotal, getDelta(curTotal-lastTotal))
if len(totCleared) > 0:
    body += "(<a href=\"https://bugzilla.mozilla.org/buglist.cgi?bug_id=%s\">Cleared %s</a>, " % (join(totCleared,","), len(totCleared))
else: body += "(Cleared 0, "
if len(totAdded) > 0:
    body += "<a href=\"https://bugzilla.mozilla.org/buglist.cgi?bug_id=%s\">Added %s</a>)</td>\n</tr>\n" % (join(totAdded,","), len(totAdded))
else: body += "Added 0)</td></tr>\n"
body += "</table>\n"

# show top teams with security bugs
i = 0
curDate = getThisWeekDate()

# Keep track of how many bugs of each severity each team has open
teamStats = {}

# Risk scoring rubric: assigns point value to each severity of bug
weights = { "sg_critical": 5,
            "sg_high":     4,
            "sg_moderate": 2,
            "sg_low":      1}

# Figure out how many open bugs (and cummulative risk index) each team has
for team in TEAMS:
    teamName = team[0]
    sql = "SELECT Stats.category, Details.date, GROUP_CONCAT(Details.bug_list) AS bugs FROM Details INNER JOIN Stats ON Details.sid=Stats.sid WHERE Details.date LIKE '%s%%' AND Stats.category IN ('sg_critical','sg_high','sg_moderate','sg_low') AND (%s) GROUP BY category;" % (curDate, team[1])
    c.execute(sql)
    rows = c.fetchall()

    # print "** %s **" % team[0]
    # Keep track of the list of each category of bugs for each team and the
    # weighted risk index
    teamStats[teamName] = {"sg_critical": "", "num_sg_critical": 0,
                           "sg_high":     "", "num_sg_high":     0,
                           "sg_moderate": "", "num_sg_moderate": 0,
                           "sg_low":      "", "num_sg_low":      0,
                           "score":        0}
    for row in rows:
        # print "%s: %d" % (row["category"], len(row["bugs"].split(",")))
        # Store the list of bugs
        teamStats[teamName][row["category"]] = row["bugs"]
        count = len(row["bugs"].split(",")) if len(row["bugs"]) else 0
        teamStats[teamName]["num_" + row["category"]] += count
        # Add points to score - critical: 5, high: 4, moderate: 2, low: 1
        points = weights[row["category"]] * count
        teamStats[teamName]["score"] += points

# calculate some totals
totalRisk = sum([t[1]["score"] for t in teamStats.items()])
totalCritical = sum([t[1]["num_sg_critical"] for t in teamStats.items()])
totalHigh = sum([t[1]["num_sg_high"] for t in teamStats.items()])
totalModerate = sum([t[1]["num_sg_moderate"] for t in teamStats.items()])
totalLow = sum([t[1]["num_sg_low"] for t in teamStats.items()])

# Sort the list of teams by their risk index
sortedTeams = sorted(teamStats.items(), key = lambda k: k[1]["score"],
                     reverse = True)

# "Risk Index By Team" table
body += "<h2>Risk Index By Team</h2>\n<table>\n<tr><th>Rank</th><th>Team</th></th><th>Risk Index</th><th>Critical</th><th>High</th><th>Moderate</th><th>Low</th></tr>\n"
i = 0

# Add a table row for each team
for s in sortedTeams:
    # ('GFX', {'score': 13, 'sg_critical': '',
    #          'sg_low': '563740,566209,455573,322708,351800,103454,563838,304123',
    #          'sg_moderate': '', 'sg_high': '575294'})
    if i%2 == 0: body += "<tr class=\"gray\">\n"
    else: body += "<tr>\n"
    # rank, team, score
    body += "  <td class=\"number\">%d</td><td>%s</td><td class=\"number\">%d</td>" % \
        (i+1, s[0], s[1]["score"])
    # critical
    numCritical = len(s[1]["sg_critical"].split(",")) if len(s[1]["sg_critical"]) else 0
    if numCritical > 0:
        body += "<td class=\"number\"><a href=\"https://bugzilla.mozilla.org/buglist.cgi?bug_id=%s\">%s</a></td>" % (s[1]["sg_critical"], numCritical)
    else:
        body += "<td class=\"number\">0</td>"
    # high
    numHigh = len(s[1]["sg_high"].split(",")) if len(s[1]["sg_high"]) else 0
    if numHigh > 0:
        body += "<td class=\"number\"><a href=\"https://bugzilla.mozilla.org/buglist.cgi?bug_id=%s\">%s</a></td>" % (s[1]["sg_high"], numHigh)
    else:
        body += "<td class=\"number\">0</td>"
    # moderate
    numModerate = len(s[1]["sg_moderate"].split(",")) if len(s[1]["sg_moderate"]) else 0
    if numModerate > 0:
        body += "<td class=\"number\"><a href=\"https://bugzilla.mozilla.org/buglist.cgi?bug_id=%s\">%s</a></td>" % (s[1]["sg_moderate"], numModerate)
    else:
        body += "<td class=\"number\">0</td>"
    # low
    numLow = len(s[1]["sg_low"].split(",")) if len(s[1]["sg_low"]) else 0
    if numLow > 0:
        body += "<td class=\"number\"><a href=\"https://bugzilla.mozilla.org/buglist.cgi?bug_id=%s\">%s</a></td>" % (s[1]["sg_low"], numLow)
    else:
        body += "<td class=\"number\">0</td></tr>\n"
    i += 1

# add totals to bottom
if i%2 == 0: body += "<tr class=\"gray\">\n"
else: body += "<tr>\n"
body += "<td class=\"total\">&nbsp;</td><td class=\"total\">&nbsp;</td><td class=\"total number\">%d</td><td class=\"total number\">%d</td><td class=\"total number\">%d</td><td class=\"total number\">%d</td><td class=\"total number\">%d</td></tr>\n" % (totalRisk, totalCritical, totalHigh, totalModerate, totalLow)

# finish up Team rank table and scoring rubric
body += "</table>\n<br>\n"
body += """<table class="medium">
<tr><th rowspan="2" class="bright">Scoring</th><td class="bright">Severity</td><td>Critical</td><td>High</td><td>Moderate</td><td>Low</td></tr>
<tr><td class="bright">Weight</td><td class="number">5</td><td class="number">4</td><td class="number">2</td><td class="number">1</td></tr>
</table>
<br>"""

# embed chart of historic risk index
body += "<h2>Historic Risk Index by Team</h2><img src=\"cid:image1\"><br>\n"

# finish up the email message
body += "<p>For charts and further details regarding Mozilla Security Bug Statistics please visit:</p>\n<p><a href=\"http://bsterne.mv.mozilla.com/secbugstats\">http://bsterne.mv.mozilla.com/secbugstats</a></p>\n<p><a href=\"http://bsterne.mv.mozilla.com/secbugstats/teams/\">http://bsterne.mv.mozilla.com/secbugstats/teams/</a></p>\n</body>\n</html>"

# set up multipart email message
msgRoot = MIMEMultipart("related")
msgRoot["Subject"] = "Weekly Security Bug Stats Report"
msgRoot["From"] = EMAIL_FROM
msgRoot["To"] = ",".join(EMAIL_TO)
msgRoot.preamble = "This is a multi-part message in MIME format."

# Plaintext body
msgAlternative = MIMEMultipart("alternative")
msgRoot.attach(msgAlternative)
msgText = MIMEText("Plain text alternative not supported.")
msgAlternative.attach(msgText)

# HTML body
msgText = MIMEText(body, "html")
msgAlternative.attach(msgText)

# image attachment
files = os.popen("find %s -name '*.png'" % JSONLOCATION)
img = files.readline().strip()
if img:
    fp = open(img, "rb")
    msgImage = MIMEImage(fp.read())
    fp.close()
    msgImage.add_header("Content-ID", "<image1>")
    msgRoot.attach(msgImage)

# if console is chosen, print only to the console
if "--console" in sys.argv:
    print "\n", msgRoot.as_string()
# print out only HTML body
elif "--html" in sys.argv:
    print "\n", body
# send out the mail
else:
    s = smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT)
    s.login(LDAP_USER, LDAP_PASS)
    s.sendmail(EMAIL_FROM, EMAIL_TO, msgRoot.as_string())