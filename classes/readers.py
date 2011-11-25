#!/usr/bin/env python
"""Lectores para text2db.

Estas clases reciben interpretan datos desde distintos medios y los transforman
en diccionarios clave valor para enviarlos al core. Deben ser iteradores ya que 
el core los tratara como tal.
"""


import logging
import sys

__author__ = "Roberto Abdelkader"
__credits__ = ["Roberto Abdelkader"]
__license__ = "GPL"
__version__ = "1.0"
__maintainer__ = "Roberto Abdelkader"
__email__ = "contacto@robertomartinez.es"
__status__ = "Production"

class Reader(object):
    """
        Clase padre de los lectores. 
    """

    def __init__(self, config, name):
        self.name = name
        self.type = self.__class__.__name__.lower()
        self.log = logging.getLogger('main.reader.%s' % self.name)
        self.config = config
        self.log.debug("Reader (%s) starting..." % self.name)

    def start(self):
        pass

    def finish(self):
        pass

class command(Reader):
    """
        Lector command.
            Ejecuta un comando y devuelve su resultado.
            Soporta reemplazo de argumentos.
    """

    def __init__(self, config, name, input_files):
        self._subprocess = __import__('subprocess')
       
        super(command, self).__init__(config, name)

        commands = self.config.c.items(self.name)
        commands = dict(filter(lambda x: x[0].startswith('exec_'), commands))

        self.strip = self.config.get(self.name, "strip", "boolean", True)

        self.command = {}
        for name, exestr in commands.iteritems():
            self.command[name[5:]] = exestr

    def next(self, extra_data = None):

        data = {}
        if extra_data:
            data.update(extra_data)

        for name, exestr in self.command.iteritems():
            if extra_data:
                exestr = exestr % extra_data

            exestr = filter(lambda x: x, exestr.split(' '))

            if self.strip:
                data[name] = self._subprocess.Popen(exestr, stdout=self._subprocess.PIPE).communicate()[0].rstrip('\r\n')
            else:
                data[name] = self._subprocess.Popen(exestr, stdout=self._subprocess.PIPE).communicate()[0]

        return data

class regexp(Reader):
    """
        Clase reader (iterable). Recibe un fichero o nombre
         de fichero y una expresion regular. Parsea cada linea
         y devuelve el diccionario de valores parseados.
    """

    #import re
    #from copy import copy

    def __init__(self, config, name, input_files):
        self._re = __import__('re')
        self._copy = __import__('copy')
       
        super(regexp, self).__init__(config, name)

        _regexp = self.config.get(self.name, "regexp")

        if type(input_files) != list:
            self.original_input_files = [ input_files ]
        else:
            self.original_input_files = input_files

        try:
            self._regexp = [self._re.compile(_regexp)]
            self.long_regexp = False
        except:
            # Python no soporta mas de 100 grupos nominales.
            # Como "probablemente" estemos utilizando una expresion regular para capturar
            # campos de ancho fijo, generaremos N expresiones regulares con un maximo 
            # de 100 campos nominales cada una
            
            self.long_regexp = True
            self._regexp = []
            splitregexp = self._re.compile("[^)]*\(\?P.*?\)[^(]*")
            groups = splitregexp.findall(_regexp)
            while groups:
                self._regexp.append(self._re.compile("".join(groups[0:99])))
                del groups[0:99]

        self.skip_empty_lines = self.config.get(self.name, "skip_empty_lines", "boolean", True)

        self.cyclic = self.config.get(self.name, "cyclic", "boolean", False)
 
        self.delete_extra_spaces = self.config.get(self.name, "delete_extra_spaces", "boolean", True)

        self.skip_first_line = self.config.get(self.name, "skip_first_line", "boolean", False)


        static_fields=self.config.get(self.name, "static_fields")
        if static_fields and type(static_fields) == str:
            self.static_fields = dict()
            for item in static_fields.split(","):
                item = item.strip()
                key, value = item.split("=")
                key = key.strip()
                value = value.strip()
                self.static_fields[key] = value
        else:
            self.static_fields = None

        self.line = ""
        self.line_number = 0

        self._next_file()
        self.log.debug("File reader started...")

    def __del__(self):
        self.input_file.close()

    def __iter__(self):
        return self


    def start(self):
        self.input_files = self._copy.copy(self.original_input_files)
        self._next_file()
    
    def _next_file(self):

        try:
            self.input_files
        except:
            self.input_files = self._copy.copy(self.original_input_files)

        if self.input_files:
            self.current_file = self.input_files.pop()
        elif self.cyclic:
            self.input_files = self._copy.copy(self.original_input_files)
            self.current_file = self.input_files.pop()
        else:
            raise StopIteration

        self.log.debug("Opening file (%s)" % self.current_file)
        self.input_file = open(self.current_file, 'r')

        if self.skip_first_line:
            self.log.warning("Skipping first line...")
            self.input_file.readline()

            
    def next(self, extra_data = None):

        self.line = self.input_file.readline() 
        self.line_number += 1
        while self.skip_empty_lines and self.line == "\n":
            self.log.warning("Skipping empty line. #%s" % self.line_number )
            self.line = self.input_file.readline() 
            self.line_number += 1
            
        if not self.line:
            self.log.debug("End of file (%s)" % self.current_file)
            self._next_file()
            return self.next()

        self.log.debug("Line #%s : %s" % (self.line_number, self.line))

        # 100 groups regexp workaround 
        subline = self.line
        result = []
        data = {}
        for subregexp in self._regexp:
            subresult = subregexp.search(self.line) 
            if subresult:
                # Delete matched line part
                subline = subline[subresult.span()[1]:]
                subdata = subresult.groupdict() 
                data.update(subdata)

        if data:
            if self.delete_extra_spaces:
                data = dict(zip(data.keys(), map(lambda x: x.strip(), data.values())))

            if self.static_fields:
                data = dict(data.items() + self.static_fields.items())

            self.log.debug("Data found: %s" % data)

            if extra_data and type(extra_data) == dict:
                data.update(extra_data)

            return data
        else:
            self.log.warning("No data found at line #%s" % self.line_number)
            if extra_data and type(extra_data) == dict:
                return extra_data
            return None

