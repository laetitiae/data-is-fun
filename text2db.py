#!/usr/bin/env python
"""Text2DB. Genera bases de datos a partir de otros formatos.

....................                       .....................
.                  .                       .                   .
.                  .                       .                   .
.     READERS      .                       .      WRITERS      .
.                  .                       .                   .
.                  .                       .                   .
....................                       .....................
        ^          ..                    ..         |           
        |            ..                ..           v           
                       ................            ___          
       /-/|            .              .           (___)         
      /_/ |            .              .           |   |         
      | |/|            .     CORE     .           |   |         
      | | |            .              .           |   |         
      |_|/             .              .           |___|         
     PLAIN             ................          DATABASE       
       FORMAT
"""


import re
import os
import sys
import logging
import getopt

# Add class dir to the path
BASE_DIR = os.path.dirname(__file__) or '.'
CLASS_DIR = os.path.join(BASE_DIR, 'classes')
sys.path.insert(0, CLASS_DIR)

from config import Config

try:
    import progressbar
    progress = True
except:
    progress = False

__author__ = "Roberto Abdelkader"
__credits__ = ["Roberto Abdelkader"]
__license__ = "GPL"
__version__ = "1.0"
__maintainer__ = "Roberto Abdelkader"
__email__ = "contacto@robertomartinezp.es"
__status__ = "Production"

class Text2Db:
    

    def __init__(self, config, files_to_read = {}):
        
        self.version = "2.0"
        self.log = logging.getLogger('main.core')
        self.config = config

        self.log.info("Text2DB Started! v.%s", self.version)

#        on_error = self.config.get("main", "on_error", "string", "rollback")
#        inspect = self.config.get("main", "inspect", "boolean", True)

        task_list = self.config.get("main", "process", "string", "reader > writer")
        object_list = set(re.findall('([a-zA-Z_0-9]+)', task_list))

        self.objects = self.map_objects(object_list, files_to_read)
        # Do all tasks
        for number, task in enumerate(task_list.split('&'), 1):
            print "Starting task %s" % number
            task = task.replace(' ','').replace('(','[').replace(')',']')
            task = re.sub(r'(?<=.)?([a-zA-Z_0-9]+)(?=.)?', r'"\1"', task)
            task_reader, task_writer = task.split('>')

            writer_part = eval('[%s]' % task_writer)
            reader_part = eval('[%s]' % task_reader)


            for writer_group in writer_part:
                if type(writer_group) is not list:
                    writer_group = [ writer_group ]

                # Initialize current writers
                for current_writer in writer_group:
                    self.objects[current_writer].start()

                for reader_group in reader_part:
                    print "%s > %s" % (reader_group, writer_group)
                    if type(reader_group) is not list:
                        reader_group = [ reader_group ]

                    # Initialize current readers
                    for current_reader in reader_group:
                        self.objects[current_reader].start()
   
                    data = self.objects[reader_group[0]].next()
                    while data:
                        # Get and append data of all readers
                        for reader in reader_group[1:]:
                            data = self.objects[reader].next(data)
   
                        # Send accumulated data to all writers
                        for current_writer in writer_group:
                            self.objects[current_writer].add_data(data)

                        try:
                            data = self.objects[reader_group[0]].next()
                        except:
                            break

                    # Finish current readers
                    for current_reader in reader_group:
                        self.objects[current_reader].finish()

                # Finish current writers
                for current_writer in writer_group:
                    self.objects[current_writer].finish()

                
        sys.exit(0)                

        #
        # File inspection
        #
        if inspect:
            # Inspect files before insert
            try:
                w = dbinspector(c)
            except Exception, e:
                self.log.error("Error starting database inspector")
                self.log.exception(e)
                sys.exit(1)

            for filename in files_to_read:
                try:
                    del r
                except:
                    pass

                self.log.info("Inspecting file: " + filename)
                if progress: # First count lines
                    widgets = [os.path.basename(filename) + ': ', progressbar.Percentage(), ' ', progressbar.Bar(marker='*',left='[',right=']'), ' ', progressbar.ETA(), ' ', progressbar.FileTransferSpeed()]
                    pbar = progressbar.ProgressBar(widgets=widgets, maxval=file_len(filename))
                    pbar.start()

                r = reader(c, filename)

                query_type = self.config.get("writer", "query_type", "string", default="insert") 
                query_where = self.config.get("writer", "query_where", "string", default="")
                try:
                    for data in r:
                        w.add_data(data)
                        if progress:
                            pbar.update(w.added)
                
                    self.log.info("File " + filename + " successfully processed.")
                    if progress:
                        pbar.finish()
                except (KeyboardInterrupt, SystemExit):
                    self.log.info("User exit while inspecting")
                    sys.exit(2)
                except Exception, e:
                    self.log.exception(e)
                    self.log.info("Error detected while inspecting")
                    sys.exit(1)

            # Commit changes
            w.finish()
            del w

        #
        # Insert data
        #
        try:
            w = dbwriter(c)
        except Exception, e:
            self.log.error("Error starting database writer")
            self.log.exception(e)
            sys.exit(1)

        for filename in files_to_read:
            try:
                del r
            except:
                pass

            self.log.info("Processing file: " + filename)
            if progress: # First count lines
                widgets = [os.path.basename(filename) + ': ', progressbar.Percentage(), ' ', progressbar.Bar(marker='*',left='[',right=']'), ' ', progressbar.ETA(), ' ', progressbar.FileTransferSpeed()]
                pbar = progressbar.ProgressBar(widgets=widgets, maxval=file_len(filename))
                pbar.start()

            r = reader(c, filename)

            query_type = self.config.get("writer", "query_type", "string", default="insert") 
            query_where = self.config.get("writer", "query_where", "string", default="")
            try:
                for data in r:
                    sql_query = w.make_query(data, query_type = query_type, query_where = query_where)
                    if sql_query:
                        w.do_query(sql_query)
                    elif on_error == "pass":
                        self.log.warning("Invalid query, not inserting! Maybe malformed regexp or malformed line?")
                    else:
                        raise Exception("Empty query!, maybe malformed regexp?")
                    if progress:
                        pbar.update(w.added)
            
                self.log.info("File " + filename + " successfully processed.")
                if progress:
                    pbar.finish()
                w.do_commit()
            except (KeyboardInterrupt, SystemExit):
                self.log.info("User exit, doing action: " + on_error)
                w.do_rollback()
                sys.exit(2)
            except Exception, e:
                self.log.exception(e)
                if on_error == "pass":
                    self.log.error("Error detected, doing action: " + on_error)
                    pass
                else:
                    self.log.error("Error detected, doing default action: rollback")
                    w.do_rollback()
                    sys.exit(1)

        self.log.info("Done!, exiting...")
        sys.exit(0)


    def map_objects(self, object_list, files_to_read):
        objects = {}

        for name in object_list:
            try:
                object_type, object_subtype = self.config.get(name, "type", "string", "").split(':', 1)
            except ValueError:
                print "Bad type"



            try:
                object_type = object_type.lower()
                object_subtype = object_subtype.lower()

                if object_type == "readers":
                    if files_to_read.has_key(name):
                        files = files_to_read[name]
                    elif files_to_read.has_key('_all'):
                        files = files_to_read['_all']
                    else:
                        files = []
                    # Import the module and set object
                    exec("from %s import %s\nobjects[\"%s\"]=%s(self.config, name, files)" % (object_type, object_subtype, name, object_subtype))
                elif object_type == "writers":
                    # Import the module and set object
                    exec("from %s import %s\nobjects[\"%s\"]=%s(self.config,name)" % (object_type, object_subtype, name, object_subtype))
                else:
                    raise TypeError

            except Exception, e:
                print "Import error (%s)" % e
                raise

        return objects

def file_len(fname):
    try:
        f = open(fname)
        for i, l in enumerate(f):
            pass
        return i + 1
    except:
        return 0

def usage():
    print "usage: text2db [-c|--config] <configfile> [-h|--help] [-q|--quiet] [-d|--debug] (<files_to_read> | [--reader_1_name]=[file1...fileN] [--reader_2_name]=[file1...fileN])"
    print "   -c|--config\tSet config file"
    print "   -h|--help\tShow this help and exit"
    print "   -q|--quiet\tSuppress messages"
    print "   -d|--debug\tEnable debug mode"
    print ""
    sys.exit(2)

if __name__ == '__main__':

    #
    # Parse command line options 
    #
        
    try:
        opts, files_to_read = getopt.getopt(sys.argv[1:], "hqc:d", ["help", "quiet", "config=", "debug"])
    except getopt.GetoptError, err:
        opts = re.findall("(?:^|)(-{1,2}[a-zA-Z0-9]+)=?\s*(.*?)(?=(?:\s-{1,2}|$))", " ".join(sys.argv[1:]))
        files_to_read = None

    verbose_level = None
    config_file = None

    files_by_reader = {}
    for optlist, arglist in opts:
        if optlist in ("-q", "--quiet"):
            verbose_level = 0 
        elif optlist in ("-d", "--debug"):
            verbose_level = 3
        elif optlist in ("-h", "--help"):
            usage()
        elif optlist in ("-c", "--config"):
            config_file = arglist
        else:
            try:
                files_by_reader[optlist[2:]] += [ x.strip(' ') for x in arglist.split(' ') ]
            except:
                files_by_reader[optlist[2:]] = [ x.strip(' ') for x in arglist.split(' ') ]

    if files_to_read:
        files_by_reader['_all'] = files_to_read


    if not config_file:
        usage()

    #
    # Load config from file
    #
    c = Config(config_file)

    # 
    # Start logger
    #
    if verbose_level == None:
        verbose_level = c.get("main", "verbose", "int", 2)

    if verbose_level == 0: # TOTALY QUIET
        verbose_level = logging.CRITICAL
        progress = False
    elif verbose_level == 1:
        verbose_level = logging.ERROR
    elif verbose_level == 2:
        verbose_level = logging.INFO
    else:
        verbose_level = logging.DEBUG
        progress = False

    log_file = c.get("main", "log_file", "string", None)
    log_format = '%(asctime)s [%(levelname)s] - %(message)s'

    log = logging.getLogger('main')
    if log_file:
        logging.basicConfig(filename=log_file, level=verbose_level, format=log_format)
    else:
        logging.basicConfig(level=verbose_level, format=log_format)

    text2db = Text2Db(c, files_by_reader)

