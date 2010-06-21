import re
import json
import fnmatch

import cssutils

def test_css_file(err, filename, data, line_start=1):
    "Parse and test a whole CSS file."
    
    tokenizer = cssutils.tokenize2.Tokenizer()
    token_generator = tokenizer.tokenize(data)
    
    try:
        _run_css_tests(err, token_generator, filename, line_start - 1)
    except UnicodeDecodeError:
        err.warning("Unicode decode error.",
                    """While decoding a CSS file, an unknown character
                    was encountered, causing some problems.""",
                    filename)
    
def test_css_snippet(err, filename, data, line):
    "Parse and test a CSS nugget."
    
    # Re-package to make it CSS-complete
    data = "#foo{%s}" % data
    
    test_css_file(err, filename, data, line)
    
def _run_css_tests(err, tokens, filename, line_start=0):
    """Processes a CSS file to test it for things that could cause it
    to be harmful to the browser."""
    
    last_descriptor = None
    
    skip_types = ("S", "COMMENT")
    
    for (tok_type, value, line, position) in tokens:
        
        # Save the last descriptor for reference.
        if tok_type == "IDENT":
            last_descriptor = value.lower()
            if value.startswith("-webkit"):
                err.error("Blasphemy.",
                          "WebKit descriptors? Really?",
                          filename,
                          line)
                  
        elif tok_type == "URI":
            
            # If we hit a URI after -moz-binding, we may have a
            # potential security issue.
            if last_descriptor == "-moz-binding":
                # We need to make sure the URI is not remote.
                value = value[4:-1].strip('"\'')
                
                # Ensure that the resource isn't remote.
                if not fnmatch.fnmatch(value, "chrome://*/content/*"):
                    err.error("Cannot reference external scripts.",
                              """-moz-binding cannot reference external
                              scripts in CSS. This is considered to be
                              a security issue. The script file must be
                              placed in the /content/ directory of the
                              package.""",
                              filename,
                              line)
            
        elif tok_type == "HASH":
            # Search for interference with the identity box.
            if value == "#identity-box":
                err.warning("Modification to identity box.",
                            """The identity box (#identity-box) is a
                            sensitive piece of the interface and should
                            not be modified.""",
                            filename,
                            line)
    
