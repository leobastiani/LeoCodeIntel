import os
import re
import sublime
import sublime_plugin
import glob




extToSyntax = { #all allowed syntax
    'cpp': 'C++',
    'c': 'C++',
    'js': 'JavaScript',
    'java': 'Java',
    'py': 'Python',
    'json': 'JSON',
    'html': 'HTML',
    'htm': 'HTML',
}




DEBUG = False #if true, see some comments on console



class LeoCodeIntelEventListener(sublime_plugin.EventListener):




    def __init__(self):
        self.completions = [] # aqui vao todos os snippets, é regenerado a todo momento # all snippets, it will be regenerate everytime
        self.files = {} # aqui vao todos os arquivos # all files
        # self.files['file.c']['func'] vao todas as palavras # self.files['file.c']['func'] == self.completions['func']

        # define as Settings
        self.settings = None # será um dict: nome da setting => chave
        self.pluginSettings = None # serão adquiridos na função getSetting
        self.sublimeSettings = None # serão adquiridos na função getSetting


        self.filesSyntax = {} # dicionário: filePath => syntaxe
        self.preloadFiles = None # lista com os arquivos que devem ser carregados sempre, é um glob




    def getSetting(self, settingName, defaultValue=False):
        if self.settings is None:
            # inicializa settings
            self.settings = {}
            self.pluginSettings = sublime.load_settings("leocodeintel.sublime-settings")
            self.sublimeSettings = sublime.active_window().active_view().settings()
            if DEBUG:
                print('LeoCodeIntel: leocodeintel-show_only_last_word:', self.getSetting("leocodeintel-show_only_last_word"))
                print('LeoCodeIntel: leocodeintel-preload_files:', self.getSetting("leocodeintel-preload_files"))



        if settingName in self.settings:
            # já teve a setting carregada, só devolve-la            
            return self.settings[settingName]


        # carrega a setting e devolve-a
        self.settings[settingName] = self.sublimeSettings.get(settingName, self.pluginSettings.get(settingName, defaultValue))
        return self.settings[settingName]





    def isEnabled(self, filePath):
        if filePath == None:
            # não tem arquivo salvo para comparar
            return False

        fileName, fileExt = os.path.splitext(os.path.basename(filePath))
        # remove o ponto de fileExt, de .py para py
        fileExt = fileExt[1:]


        if fileExt in extToSyntax:
            return extToSyntax[fileExt]
        else:
            # não está na lista de syntaxes habilitadas
            return False



    def getSyntax(self, filePath):
        if filePath in self.filesSyntax:
            return self.filesSyntax[filePath]


        syntax = self.isEnabled(filePath)
        self.filesSyntax[filePath] = syntax
        return syntax




    ##
    # FUNÇÕES PARA LER O ARQUIVOS
    ##
    def on_activated(self, view):
        if not view:
            return ;
        elif not self.isEnabled(view.file_name()):
            return ;
        self.loadFile(view.file_name(), False, self.getContentsFromView(view))



        # carrega os arquivos que devem ser sempre carregados
        if self.preloadFiles is None:
            # primeira vez que está carregando
            # deve resolver o glob
            self.preloadFiles = set(  # para remover duplicatas
                                sum(  # transforma lista de lista em lista
                                [glob.glob(x) for x in self.getSetting('leocodeintel-preload_files', [])], []))



        for file in self.preloadFiles:
            self.loadFile(file)



    def on_post_save_async(self, view):
        if not self.isEnabled(view.file_name()):
            return ;
        self.loadFile(view.file_name(), True, self.getContentsFromView(view))
        if DEBUG:
            print('LeoCodeIntel: completions:', self.completions)



    def on_close(self, view):
        if not self.isEnabled(view.file_name()):
            return ;
        if DEBUG:
            print('LeoCodeIntel: closed: '+os.path.basename(view.file_name()))
        self.removeFile(view.file_name())
        self.reloadCompletions()




    def on_query_completions(self, view, prefix, locations):
        if not self.isEnabled(view.file_name()):
            return []
        return self.completions




    def removeFile(self, filePath):
        '''
        this function is called when a file is removed, 
        this file will be removed from self.files too
        '''
        file_name = os.path.basename(filePath)
        path = os.path.dirname(filePath)
        if file_name in self.files:
            if DEBUG:
                print('LeoCodeIntel: removing file: '+file_name)

            # deleta o arquivo em self.files
            del self.files[file_name]
            if not os.path.exists(filePath):
                return ; # file not exists


            # abre o arquivo para remover seus includes
            with open(os.path.join(path, file_name), "r", encoding='utf-8') as file:
                contents = file.read()


            includes = self.getIncludesFromContent(filePath, contents)
            for include in includes:
                self.removeFile(os.path.join(path, include))






    # carrega o arquivo filePath
    def loadFile(self, filePath, overrideFile=False, fileContents=None):
        '''
        this function will load a file in self.files
        '''

        file_name = os.path.basename(filePath)
        # não é necessário sobreescrever
        if file_name in self.files and not overrideFile:
            return ;
        dir_name = os.path.dirname(filePath)




        # obtem o conteúdo se ele n foi passado
        if fileContents == None:
            if not os.path.exists(filePath):
                return ; # file not exists
            with open(filePath, 'r', encoding='utf-8') as file:
                fileContents = file.read()



        if DEBUG:
            print("LeoCodeIntel: loading file '"+file_name+"'")




        # reseta os snippets do arquivo file_name # clear all snippets of file_name
        self.files[file_name] = {}




        #adding importantWords
        importantWords = self.getImportantWordsFromContent(filePath, fileContents)
        for word in importantWords:
            # adiciona o nome do arquivo como comentário
            self.files[file_name][word+'\t'+file_name] = word




        #adicionando funcoes do tipo int func(parameters) # adding functions like int func(parameters)
        funcs = self.getFunctionsFromContent(filePath, fileContents)
        for (type, func_name, parameters) in funcs:
            # quebra os parametros em vírgula, se não vieram quebrados
            paramSplitted = re.split('\s*,\s*', parameters) if not isinstance(parameters, list) else parameters
            lastWords = []


            for i, arg in enumerate(paramSplitted):
                if arg == '':
                    continue


                # remove tudo que está para a direita do igual
                arg = arg.partition('=')[0]




                # ultima palavra do parametro
                search = re.search('(\w+)\s*$', arg)
                lastWord = search.group() if search is not None else arg
                lastWords += [lastWord]



                if not self.getSetting("leocodeintel-show_only_last_word", False):
                    # já é o próprio arg
                    snippet_word = arg


                else:
                    # troca os snippet
                    snippet_word = lastWord
                    

                paramSplitted[i] = '${'+str(i+1)+':'+snippet_word+'}'



            complemento = ', '.join(lastWords)
            if complemento == '': complemento = '()'
            self.files[file_name][func_name+'\t'+complemento] = func_name+'('+', '.join(paramSplitted)+')'



        #adicionando includes # adding files in #include "file"
        includes = self.getIncludesFromContent(filePath, fileContents)
        for include in includes:
            self.loadFile(os.path.join(dir_name, include))
        self.reloadCompletions()





    def reloadCompletions(self):
        '''
        this function makes self.completions
        '''
        if DEBUG:
            print('LeoCodeIntel: reloading completions')
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







    def getIncludesFromContent(self, filePath, fileContents):
        '''
        return all files that is mettioned in #include "file.c"
        ['file1', 'file2', 'file3']
        '''
        syntax = self.getSyntax(filePath)
        if syntax == 'C++':
            result = re.findall(r'#\s*include\s*\"([^\"]+)\"', 
                    fileContents)


        else:
            return []



        return result






    def getFunctionsFromContent(self, filePath, fileContents):
        '''
        return all functions like (type, func_name, parameters)
        or (type, func_name, [param1, param2, param3])
        '''
        syntax = self.getSyntax(filePath)
        if syntax == 'C++':
            result = re.findall(r'(\w+)\**\s+(?:\w+\s+)*\**\s*(?:\w+\:\:)?(\w+)\s*\(([^\)]*)\)', 
                fileContents)



        elif syntax == 'JavaScript':
            # funções do tipo func_name = function () {}
            result = re.findall(r'(\w+)\s+=\s+function\s*\(([^\)]*)\)', 
                fileContents)

            # funções do tipo function func_name() {}
            result += re.findall(r'function\s+(\w+)\s*\(([^\)]*)\)', 
                fileContents)



            # força o tipo (type, func_name, parameters)
            # se func_name for diferente de __init__, por exemplo
            result = [(None, x[0], x[1]) for x in result]




        elif syntax == 'Java':
            result = re.findall(r'\s*(?:protected|private|public)\s+(\w+\s+)*(\w+)\(([^\)]*)\)', 
                fileContents)







        elif syntax == 'Python':
            result = re.findall(r'\bdef\s+(\w+)\(([^\)]*)\)\:', 
                fileContents)


            # remove parametros com self e cls
            for i, elem in enumerate(result):
                parameters = re.split(r'\s*,\s*', elem[1])

                # se o primeiro parametro for self ou cls, pula ele
                if parameters[0] == 'self' or parameters[0] == 'cls':
                    parameters = parameters[1:]

                result[i] = [result[i][0], parameters]



            result = [(None, x[0], x[1]) for x in result if not re.match('\_\_\w+\_\_', x[0])]







        else:
            return []




        # remove resultados não desejados
        result = [x for x in result if x[1] not in ('main', 'if', 'elif') and x[0] != 'return']
        return result








    def getImportantWordsFromContent(self, filePath, fileContents):
        '''
        return important words
        ['word1', 'word2', 'word3', ...]
        '''
        syntax = self.getSyntax(filePath)
        if syntax == 'C++':
            #adicionando palavras, tipo #define word # adding words like #define word
            result = re.findall(r'\#\s*define\s+(\w+)', 
                    fileContents)
            #adicionando palavras do tipo typedef word snippet; #adding words like typedef word
            result += re.findall(r'typedef(?:\s+\w+)+\s+(\w+)\s*;', 
                    fileContents)



        elif syntax == 'HTML':
            classesString = re.findall(r'class="(.*?)"', fileContents)
            classes = sum([re.split(r'\s+', x) for x in classesString], [])
            ids = re.findall(r'id="(.*?)"', fileContents)

            return set(classes+ids)



        elif syntax == 'JSON':
            # confere todas as aspas com apenas uma palavra
            result = re.findall(r'"(\w+)"', 
                    fileContents)



        else:
            return []


        return result
