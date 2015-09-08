import os
import re
import sublime
import sublime_plugin




syntax_list = { #all allowed syntax
    'C++': True,
    'C': True,
    'Objective-C' : True,
    'Objective-C++': True,
    'JavaScript': True,
    'Java': True
}




DEBUG = False #if true, see some comments on console
enabled = True #if true, this plugin will work, i guess... :)



class CppCodeIntelEventListener(sublime_plugin.EventListener):




    def __init__(self):
        self.completions = [] # aqui vao todos os snippets, é regenerado a todo momento # all snippets, it will be regenerate everytime
        self.files = {} # aqui vao todos os arquivos # all files
        # self.files['file.c']['func'] vao todas as palavras # self.files['file.c']['func'] == self.completions['func']
        settings = sublime.load_settings("cppcodeintel.sublime-settings")
        self.show_only_last_word = settings.get("show_only_last_word", False)
        self.syntax = None #syntax atual



    def isEnabled(self, view):
        syntax, _ = os.path.splitext(os.path.basename(view.settings().get('syntax')))
        if DEBUG:
            print('syntax: ', syntax)
        if syntax not in syntax_list or not enabled:
            return False
        elif view.file_name() == None:
            return False



        # resume a syntaxe do C++
        if syntax in ("C++", "C", "Objective-C", "Objective-C++"):
            syntax = 'C++'




        self.syntax = syntax
        return syntax_list[syntax]




    ##
    # FUNÇÕES PARA LER O ARQUIVOS
    ##
    def on_activated(self, view):
        if not view:
            return ;
        elif not self.isEnabled(view):
            return ;
        self.loadFile(view.file_name(), False, self.getContentsFromView(view))



    def on_post_save_async(self, view):
        if not self.isEnabled(view):
            return ;
        self.loadFile(view.file_name(), True, self.getContentsFromView(view))
        if DEBUG:
            print(self.completions)



    def on_close(self, view):
        if not self.isEnabled(view):
            return ;
        if DEBUG:
            print('CppCodeIntel: closed: '+os.path.basename(view.file_name()))
        self.removeFile(view.file_name())
        self.reloadCompletions()




    def on_query_completions(self, view, prefix, locations):
        if not self.isEnabled(view):
            return []
        return self.completions




    def removeFile(self, file_path):
        '''
        this function is called when a file is removed, 
        this file will be removed from self.files too
        '''
        file_name = os.path.basename(file_path)
        path = os.path.dirname(file_path)
        if file_name in self.files:
            if DEBUG:
                print('CppCodeIntel: removing file: '+file_name)

            # deleta o arquivo em self.files
            del self.files[file_name]
            if not os.path.exists(file_path):
                return ; # file not exists


            # abre o arquivo para remover seus includes
            with open(os.path.join(path, file_name), "r", encoding='utf-8') as file:
                contents = file.read()


            includes = self.getIncludesFromContent(contents)
            for include in includes:
                self.removeFile(os.path.join(path, include))






    # carrega o arquivo file_path
    def loadFile(self, file_path, override_file=False, file_contents=None):
        '''
        this function will load a file in self.files
        '''

        # obtem o conteúdo se ele n foi passado
        if file_contents == None:
            if not os.path.exists(file_path):
                return ; # file not exists
            with open(file_path, 'r', encoding='utf-8') as file:
                file_contents = file.read()




        file_name = os.path.basename(file_path)
        dir_name = os.path.dirname(file_path)


        # não é necessário sobreescrever
        if not (file_name not in self.files or override_file):
            return ;



        if DEBUG:
            print("CppCodeIntel: loading file '"+file_name+"'")



        #cleaning the file
        # file_contents = self.cleanCode(file_contents)
        




        # reseta os snippets do arquivo file_name # clear all snippets of file_name
        self.files[file_name] = {}




        #adding important_words
        important_words = self.getImportantWordsFromContent(file_contents)
        for word in important_words:
            self.files[file_name][word] = word




        #adicionando funcoes do tipo int func(parameters) # adding functions like int func(parameters)
        funcs = self.getFunctionsFromContent(file_contents)
        for (type, func_name, parameters) in funcs:
            count = 1
            params_splited = parameters.split(', ')
            for i, arg in enumerate(params_splited):
                if arg == '':
                    continue
                elif self.show_only_last_word == False:
                    snippet_word = arg
                else:
                    try:
                        snippet_word = re.search('\w+(?:\[(?:\w+)?\])*$', arg).group()
                    except:
                        snippet_word = arg
                params_splited[i] = '${'+str(count)+':'+snippet_word+'}'
                count += 1
            self.files[file_name][func_name] = func_name+'('+', '.join(params_splited)+')'



        #adicionando includes # adding files in #include "file"
        includes = self.getIncludesFromContent(file_contents)
        for include in includes:
            self.loadFile(os.path.join(dir_name, include))
        self.reloadCompletions()





    def reloadCompletions(self):
        '''
        this function makes self.completions
        '''
        if DEBUG:
            print('CppCodeIntel: reloading completions')
            print('\tfiles to process: '+', '.join(self.files.keys()))
        del self.completions[:]
        funcs = {} # todas as funcoes definidas
        for file in self.files.values():
            for func in file:
                if func not in funcs:
                    self.completions += [(func, file[func])]
                    funcs[func] = True





    def getContentsFromView(self, view):
        '''
        return the contents inside the view
        '''
        return view.substr(sublime.Region(0, view.size()))







    def getIncludesFromContent(self, file_contents):
        '''
        return all files that is mettioned in #include "file.c"
        ['file1', 'file2', 'file3']
        '''
        if self.syntax == 'C++':
            result = re.compile(
                '#\s*include\s*\"([^\"]+)\"'
            ).findall(file_contents)


        else:
            return []



        return result






    def getFunctionsFromContent(self, file_contents):
        '''
        return all functions like (type, func_name, parameters)
        '''
        if self.syntax == 'C++':
            result = re.compile(
                '(\w+)\**\s+(?:\w+\s+)*\**\s*(?:\w+\:\:)?(\w+)\s*\(([^\)]*)\)'
            ).findall(file_contents)



        elif self.syntax == 'JavaScript':
            # funções do tipo func_name = function () {}
            result = re.compile(
                '(\w+)\s+=\s+function\s*\(([^\)]*)\)'
            ).findall(file_contents)

            # funções do tipo function func_name() {}
            result += re.compile(
                'function\s+(\w+)\s*\(([^\)]*)\)'
            ).findall(file_contents)



            # força o tipo (type, func_name, parameters)
            result = [(None, x[0], x[1]) for x in result]




        elif self.syntax == 'Java':
            result = re.compile(
                '\s*(?:protected|private|public)\s+(\w+\s+)*(\w+)\(([^\)]*)\)'
            ).findall(file_contents)




        else:
            return []




        # remove resultados não desejados
        result = [x for x in result if x[1] not in ('main', 'if', 'elif') and x[0] != 'return']
        return result








    def getImportantWordsFromContent(self, file_contents):
        '''
        return important words
        ['word1', 'word2', 'word3', ...]
        '''
        if self.syntax == 'C++':
            #adicionando palavras, tipo #define word # adding words like #define word
            result = re.compile(
                '\#\s*define\s+(\w+)'
                ).findall(file_contents)
            #adicionando palavras do tipo typedef word snippet; #adding words like typedef word
            result += re.compile(
                'typedef(?:\s+\w+)+\s+(\w+)\s*;'
            ).findall(file_contents)


        else:
            return []


        return result






    def cleanCode(self, file_contents):
        '''
        remove all comments and non important code
        '''
        #removing comments
        file_contents = re.sub('//[^\n]*\n?', '\n', file_contents)
        file_contents = re.sub('\/\*.*?\*\/', '', file_contents)



        # removing {|} inside in strings
        file_contents = re.sub('".*(\{|\}).*"', '', file_contents)
        file_contents = re.sub("'.*(\{|\}).*'", '', file_contents)




        # se a linguagem possuir conteudo significante
        # dentro dos { }, retorna agora
        if self.syntax == 'Java':
            return file_contents





        #removing {}
        result = ''
        opened_brackets = 0
        for char in file_contents:
            if char == '{':
                opened_brackets+=1
            elif char == '}':
                opened_brackets-=1
            elif opened_brackets == 0:
                result += char



        return result