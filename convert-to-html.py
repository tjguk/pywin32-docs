from __future__ import with_statement
import os, sys
import datetime
import htmlentitydefs
import itertools
import operator
import posixpath
import re
import sgmllib
import shutil
import tempfile

site_packages = os.path.join(sys.exec_prefix, "lib", "site-packages")
chm_filepath = os.path.join(site_packages, "pywin32.chm")
with open(os.path.join(site_packages, "pywin32.version.txt")) as f:
        pywin32_version = f.read().strip()

class FixupParser(sgmllib.SGMLParser):
    """Fix-up parser to scan the contents file generated
    by HTMLHelp, generate a suitable HTML output file for
    use within standard HTML files and to provide a
    root-to-leaf mapping for use as a breadcrumb trail
    in individual pages.
    """

    def __init__(self, infile, outfile):
        sgmllib.SGMLParser.__init__(self)
        self.infile = infile
        self.outfile = outfile

        self.inside_li = False
        self.inside_object = False
        self.link_name = self.link_url = ""
        self.trail = []
        self.contents_map = {}

    def start(self):
        self.feed(self.infile.read())

    def output(self, text):
        self.outfile.write(text + "\n")

    def start_ul(self, attrs):
        """If we're starting a list, close any unclosed
        list item and add the latest(ie this) url/name
        pair to the trail."""
        if self.inside_li:
            self.end_li()
        self.output("<ul>")
        if self.link_url:
            self.trail.append((self.link_url, self.link_name))

    def end_ul(self):
        """If we're finishing a list, close any unclosed
        list item and pop this url/name off the trail."""
        if self.inside_li:
            self.end_li()
        self.output("</ul>")
        if self.trail:
            self.trail.pop()

    def start_li(self, attrs):
        """If we're starting a list item, make a note of the
        fact so we can track objects within it."""
        if self.inside_li:
            self.end_li()
        self.output("<li>")
        self.inside_li = True

    def end_li(self):
        """If we're finishing a list item, make a note so no
        objects are tracked which are outside a list item."""
        self.output("</li>")
        self.inside_li = False

    def start_object(self, attrs):
        """The text/sitemap objects hold the real indexing info.
        Note that we're inside such an object so that we pick up
        its parameters."""
        attrs = dict(attrs)
        if attrs.get("type") == "text/sitemap":
            if self.inside_object:
                self.end_object()
            self.link_name = self.link_url = ""
            self.inside_object = True

    def end_object(self):
        """At the end of an object tag, add the trail so far to
        the entry for this item's index and output an appropriate
        href."""
        if self.inside_object:
            self.contents_map[self.link_url] = self.trail[:]
            if self.trail and self.trail[-1][0] <> self.link_url:
                self.contents_map[self.link_url].append(("", self.link_name))
            self.output('<a href="%s">%s</a>' %(self.link_url, self.link_name))
            self.inside_object = False

    """An object's param items are where the indexing info is
    stored. A "Name" param holds the name of the page; a "Local"
    item holds the slightly mungified URL which we strip before
    storing."""
    def start_param(self, attrs):
        UNWANTED_PREAMBLE = "mk:@MSITStore:PyWin32.chm::/"
        if self.inside_object:
            attrs = dict(attrs)
            if attrs.get("name") == "Name":
                self.link_name = attrs.get("value", "<Unnamed>")
            elif attrs.get("name") == "Local":
                link_url = attrs.get("value")
                if link_url:
                    self.link_url = link_url[len(UNWANTED_PREAMBLE):]
                else:
                    self.link_url = "<Unlinked>"

UNWANTED_MARKUP = ["html", "body", "head"]
UNWANTED_RE = re.compile("|".join("<%s>|</%s>" %(markup, markup) for markup in UNWANTED_MARKUP), re.IGNORECASE)
UNWANTED_TITLE_RE = re.compile(r"<title>.*</title>", re.IGNORECASE)
UNWANTED_GENERATOR = r'<META NAME="GENERATOR" CONTENT="Autoduck, by erica@microsoft.com">'
UNWANTED_HR_RE = re.compile(r"<hr>", re.IGNORECASE)

def munged_text(text):
    #
    # Fix up entity & character defs so they end with semicolons
    #
    for entitydef in htmlentitydefs.entitydefs.keys():
        text = re.sub(r"(&%s)(?!;)" % entitydef, "\g<1>;", text)
    text = re.sub(r"(&#\d+)(?!;)", "\g<1>;", text)
    text = re.sub(r"<title>[^<]*</title>", "", text, re.IGNORECASE)
    text = UNWANTED_RE.sub("", text)
    text = UNWANTED_TITLE_RE.sub("", text)
    text = text.replace(UNWANTED_GENERATOR, "")
    text = UNWANTED_HR_RE.sub("", text)
    text = u"\n".join(line + u"</li>" if line.lower().startswith(u"<li>") and u"</li>" not in line.lower() else line for line in text.splitlines())
    return text

def relpath(target_url, current_url):
    target_path, target_file = posixpath.split(target_url)
    current_path, current_file = posixpath.split(current_url)

    start_list = current_path.split(os.path.sep)
    path_list = target_path.split(os.path.sep)
    i = len(os.path.commonprefix([start_list, path_list]))
    rel_list = [os.path.pardir] *(len(start_list) - i) + path_list[i:]
    return posixpath.join("/".join(rel_list), target_file)

INDEX_CONTENT = """
<h1>PyWin32 Documentation</h1>

<p>This documentation is generated from the .chm file which is shipped with
the PyWin32 extensions for Python. Apart from absolutely essential cleanups
to make the HTML display properly, no changes have been made.</p>

<p><b>Updated %s</b>: Now includes documentation up to %s</p>

<ul>
<li> <a href="contents.html">Table of Contents</a> </li>
<li> <a href="PyWin32.HTML">Front Page</a></li>
<li> <a href="html/CHANGES.txt">Project ChangeLog</a> </li>
<!-- li> <a href="changes.html">Added / Updated pages</a></li -->
</ul>
""" %(datetime.date.today(), pywin32_version)

#
# Navigation is a separate string so that it can be
# excluded from, eg, the contents page.
#
NAVIGATION_HTML = """
<div class="navigation">
    <a href="%(root_path)s%(toc_filename)s">Contents</a> | %(breadcrumbs)s
</div>
"""

HTML = """
<html>
    <head>
        <title>%(title)s</title>
        <link href="%(root_path)s%(css_filename)s" rel="stylesheet" type="text/css" media="all">
        <meta http-equiv="Content-Type" content="text/html; charset=utf-8">
    </head>
    <body>
        %(navigation)s
        <div id="content">
            %(content)s
        </div>
    </body>
</html>
"""

def fixup_isapi_links(text):
    return text.replace('href="/', 'href="../../../')

SPECIAL_PROCESSING = {
    "html/isapi/doc/isapi.html" : fixup_isapi_links
}

ARGS = set(["nogenerate", "debug", "nochanges"])
def main(args=[]):
    args = set(args)
    if not set(args) <= ARGS:
        raise RuntimeError("Arguments %s not recognised; should only be %s" %(", ".join(set(args).difference(ARGS)), ", ".join(ARGS)))

    html_tempdir = os.path.join(tempfile.gettempdir(), "pywin32-docs-htmlhelp")

    html2_tempdir = "docs"
    shutil.rmtree(html2_tempdir)
    os.mkdir(html2_tempdir)
    css_filename = "pywin32.css"
    toc_filename = "contents.html"
    changes_filename = "changes.html"

    if "nogenerate" not in args:
        print "Decompiling .chm..."
        shutil.rmtree(html_tempdir)
        os.mkdir(html_tempdir)
        os.system("hh.exe -decompile %s %s" %(html_tempdir, chm_filepath))

        print "Writing index.html..."
        with open(os.path.join(html2_tempdir, "index.html"), "w") as outfile:
            title = "PyWin32 Documentation"
            navigation = ""
            root_path = ""
            content = INDEX_CONTENT
            outfile.write(HTML % locals())

        print "Generating contents..."
        with open(os.path.join(html_tempdir, "pywin32.hhc")) as infile:
            handle, filename = tempfile.mkstemp()
            with open(filename, "w") as outfile:
                parser = FixupParser(infile, outfile)
                parser.start()
        contents_map = parser.contents_map

        print "Writing table of contents..."
        with open(os.path.join(html2_tempdir, toc_filename), "w") as outfile:
            title = "PyWin32 Documentation"
            content = open(filename).read()
            root_path = ""
            css_filename = css_filename
            navigation = ""
            outfile.write(HTML % locals())

        for html_dirname, dirnames, filenames in os.walk(html_tempdir, topdown=True):
            if "debug" in args: filenames = filenames[:30]
            html2_dirname = os.path.join(html2_tempdir, html_dirname[1+len(html_tempdir):])
            print html_dirname, "=>", html2_dirname
            if not os.path.exists(html2_dirname):
                os.mkdir(html2_dirname)

            for filename in filenames:
                if not filename.lower().endswith((".txt", ".html", ".htm")): continue
                name, ext = os.path.splitext(filename)
                filename = name + ext.lower()
                html_filepath = os.path.join(html_dirname, filename)
                html2_filepath = os.path.join(html2_dirname, filename)
                depth = html2_filepath.count("\\") - 1
                print "    %s(%d)" %(html_filepath, depth)
                root_path = "../" * depth
                relative_filepath = html_filepath[1+len(html_tempdir):].replace("\\", "/")

                content = unicode(open(html_filepath).read(), "cp1252")
                content = munged_text(content)
                special_processing = SPECIAL_PROCESSING.get(relative_filepath)
                if special_processing:
                    content = special_processing(content)
                for title in re.findall(r"<h1>([^<]+)</h1>", content, re.IGNORECASE):
                    break
                else:
                    title = filename

                breadcrumb_trail = contents_map.get(relative_filepath, [])
                breadcrumbs = u" &gt; ".join(u'<a href="%s">%s</a>' %(relpath(url, relative_filepath) if url else name, name) for(url, name) in breadcrumb_trail)
                navigation = NAVIGATION_HTML % locals()
                if filename.lower().endswith(".txt"):
                    html = content
                else:
                    html = HTML % locals()
                open(html2_filepath, "w").write(html.encode("utf8"))

    try:
        import git
    except ImportError:
        args.add("nochanges")
    else:
        #
        # FIXME: until we've got the git changes working
        #
        args.add("nochanges")
    if "nochanges" not in args:
        print "Finding changes..."
        wc = git.Repo(".")
        added = [f for f in wc.untracked_files if f.startswith(html2_tempdir) and f.endswith(".html")]
        changed = [item.a_path for item in wc.index.diff() if item.a_path.startswith(html2_tempdir) and item.a_path.endswith(".html")]
        wc.index.add(added)

        UNCHANGED = ["normal", "ignored"] ## pysvn.wc_status_kind.normal, pysvn.wc_status_kind.ignored]
        EXCLUDE_FROM_CHANGES = ["changes.html", "convert_to_html.py", "pywin32.chm"]
        wc = svn.local.LocalClient(".")
        status = list(wc.status())
        for item in status:
                if item.name.endswith(".html") and item.type_raw_name == "unversioned":
                        print "Adding", item
                        wc.add(item.name)
        changes = sorted((i for i in status if i.type_raw_name not in UNCHANGED), key=operator.attrgetter("type_raw_name"))
        content = ["<h1>PyWin32 Documentation Changes</h1>"]
        first = True
        for s, items in itertools.groupby(changes, operator.attrgetter("type_raw_name")):
            if not first: content.append("</ul>")
            content.append("<h2>%s</h2>" % s)
            content.append("<ul>")
            for item in items:
                if os.path.basename(item.name).lower() in EXCLUDE_FROM_CHANGES: continue
                content.append('<li><a href="%s">%s</a></li>' %(item.name, os.path.splitext(item.name)[0]))
            first = False
        if not first: content.append("</ul>")

        print "Writing changes..."
        with open(os.path.join(html2_tempdir, changes_filename), "w") as outfile:
            title = "PyWin32 Documentation Changes"
            content = "\n".join(content)
            root_path = ""
            css_filename = css_filename
            navigation = ""
            outfile.write(HTML % locals())

    print "Copying CSS file"
    shutil.copyfile("pywin32.css", os.path.join(html2_tempdir, "pywin32.css"))

if __name__ == '__main__':
    main(sys.argv[1:])
