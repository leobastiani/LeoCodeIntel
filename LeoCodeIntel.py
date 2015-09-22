import os
import re
import sublime
import sublime_plugin
import glob




extToSyntax = { #all allowed syntax
    'cpp': 'C++',
    'c': 'C++',
    'h': 'C++',
    'js': 'JavaScript',
    'java': 'Java',
    'py': 'Python',
    'json': 'JSON',
    'html': 'HTML',
    'htm': 'HTML',
}




DEBUG = True #if true, see some comments on console




def debug(*args):
    '''funciona como print, mas só é executada se sys.flags.debug == 1'''
    if not DEBUG:
        return ;
    print(*args)






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
        self.preloadFiles = () # lista com os arquivos que devem ser carregados sempre, é um glob



    def onLoadedSettings(self):
        # carrega os arquivos que devem ser sempre carregados
        # primeira vez que está carregando
        # deve resolver o glob
        self.preloadFiles = set(  # para remover duplicatas
                            sum(  # transforma lista de lista em lista
                            [glob.glob(x) for x in self.getSetting('preload_files', [])], []))
        # exclui os arquivos que não são desejados
        excludeFiles = self.getSetting("exclude_files", [])
        self.preloadFiles = [os.path.abspath(filePath) for filePath in self.preloadFiles if os.path.basename(filePath) not in excludeFiles]


        for file in self.preloadFiles:
            self.loadFile(file)




    def getSetting(self, settingName, defaultValue=False):
        '''retorna o valor de uma setting que pode estar
        tanto no arquivo Settings do sublime
        quanto no JSON que acompanha o plugin
        não precisa incluir leocodeintel- no parametro'''
        if self.settings is None:
            # inicializa settings
            self.settings = {}
            self.pluginSettings = sublime.load_settings("leocodeintel.sublime-settings")
            self.sublimeSettings = sublime.active_window().active_view().settings()



            # chama a função q deve ser chamada neste ponto
            self.onLoadedSettings()

        if settingName in self.settings:
            # já teve a setting carregada, só devolve-la            
            return self.settings[settingName]


        # carrega a setting e devolve-a
        realSettingName = "leocodeintel-"+settingName
        self.settings[settingName] = self.sublimeSettings.get(realSettingName, self.pluginSettings.get(realSettingName, defaultValue))
        debug('LeoCodeIntel: %s:' % settingName, self.settings[settingName])
        return self.settings[settingName]




    def getSyntaxByFilePath(self, filePath):
        if filePath == None:
            # não tem arquivo salvo para comparar
            return False



        # a syntaxe já foi consultada antes
        if filePath in self.filesSyntax:
            return self.filesSyntax[filePath]


        # obtem a syntaxe pelo nome do arquivo
        fileName, fileExt = os.path.splitext(os.path.basename(filePath))
        # remove o ponto de fileExt, de .py para py
        fileExt = fileExt[1:]


        if fileExt not in extToSyntax:
            return False

        syntax = extToSyntax[fileExt]
        self.filesSyntax[filePath] = syntax
        return syntax




    def getSyntaxByView(self, view):
        if not view:
            return False

        if view.file_name() is None:
            return False


        # a syntaxe já foi consultada antes
        filePath = view.file_name()
        if filePath in self.filesSyntax:
            return self.filesSyntax[filePath]

        # obtem a syntaxe pelo view
        syntax, _ = os.path.splitext(os.path.basename(view.settings().get('syntax')))

        # casos de C++
        if syntax in ('Objective-C++', 'Objective-C', 'C'):
            syntax = 'C++'


        if syntax not in extToSyntax.values():
            return False


        self.filesSyntax[filePath] = syntax
        return syntax




    ##
    # FUNÇÕES PARA LER O ARQUIVOS
    ##
    def on_activated(self, view):
        if not view:
            # caso de nenhum arquivo aberto
            return ;
        elif not self.getSyntaxByView(view):
            return ;
        self.loadFile(view.file_name(), False, self.getContentsFromView(view))





    def on_post_save_async(self, view):
        if not self.getSyntaxByView(view):
            return ;
        self.loadFile(view.file_name(), True, self.getContentsFromView(view))
        debug('LeoCodeIntel: completions:', self.completions)



    def on_close(self, view):
        if not self.getSyntaxByView(view):
            return ;
        debug('LeoCodeIntel: closed: '+os.path.basename(view.file_name()))
        self.removeFile(view.file_name(), self.getContentsFromView(view))
        self.reloadCompletions()




    def on_query_completions(self, view, prefix, locations):
        if not self.getSyntaxByView(view):
            return []
        return self.completions




    def removeFile(self, filePath, fileContent=None):
        '''
        this function is called when a file is removed, 
        this file will be removed from self.files too
        '''
        fileName = os.path.basename(filePath)
        dirName = os.path.dirname(filePath)
        if filePath in self.files:


            # não remove os arquivos que são sempre carregados
            if os.path.abspath(filePath) in self.preloadFiles:
                # termina a função por aqui
                return ;



            # já sei que vou remover
            debug('LeoCodeIntel: removing file: '+fileName)

            # deleta o arquivo em self.files
            del self.files[filePath]
            if not os.path.exists(filePath):
                return ; # file not exists


            # abre o arquivo para remover seus includes
            if fileContent is None:
                with open(filePath, "r", encoding='utf-8') as file:
                    fileContent = file.read()


            # remove seus includes tmb
            includes = self.getIncludesFromContent(filePath, fileContent)
            for includeName in includes:
                self.removeFile(os.path.join(dirName, includeName))






    # carrega o arquivo filePath
    def loadFile(self, filePath, overrideFile=False, fileContent=None):
        '''
        this function will load a file in self.files
        '''

        fileName = os.path.basename(filePath)
        # não é necessário sobreescrever
        if fileName in self.files and not overrideFile:
            return ;
        dir_name = os.path.dirname(filePath)




        # obtem o conteúdo se ele n foi passado
        if fileContent == None:
            if not os.path.exists(filePath):
                return ; # file not exists
            with open(filePath, 'r', encoding='utf-8') as file:
                fileContent = file.read()



        debug("LeoCodeIntel: loading file "+fileName)




        # reseta os snippets do arquivo filePath # clear all snippets of filePath
        self.files[filePath] = {}



        # carrega os snippets padrão do LeoCodeIntel, 
        snippetsPadrao = re.findall(r'\bLeoCodeIntel\s+(\S+)\s+([^\n]+)', fileContent)
        for snippet in snippetsPadrao:
            self.files[filePath][snippet[0]+'\t'+fileName] = snippet[1]




        #adding importantWords
        importantWords = self.getImportantWordsFromContent(filePath, fileContent)
        for word in importantWords:
            # adiciona o nome do arquivo como comentário
            self.files[filePath][word+'\t'+fileName] = word




        #adicionando funcoes do tipo int func(parameters) # adding functions like int func(parameters)
        funcs = self.getFunctionsFromContent(filePath, fileContent)
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



                if not self.getSetting("show_only_last_word", False):
                    # já é o próprio arg
                    snippet_word = arg


                else:
                    # troca os snippet
                    snippet_word = lastWord
                    

                paramSplitted[i] = '${'+str(i+1)+':'+snippet_word+'}'



            complemento = ', '.join(lastWords)
            if complemento == '': complemento = '()'
            self.files[filePath][func_name+'\t'+complemento] = func_name+'('+', '.join(paramSplitted)+')'



        #adicionando includes # adding files in #include "file"
        includes = self.getIncludesFromContent(filePath, fileContent)
        for include in includes:
            self.loadFile(os.path.join(dir_name, include))
        self.reloadCompletions()





    def reloadCompletions(self):
        '''
        this function makes self.completions
        '''
        debug('LeoCodeIntel: reloading completions')
        debug('\tfiles to process: '+', '.join([os.path.basename(file)+'('+self.filesSyntax[file]+')' for file in self.files.keys()]))
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







    def getIncludesFromContent(self, filePath, fileContent):
        '''
        return all files that is mettioned in #include "file.c"
        ['file1', 'file2', 'file3']
        '''
        syntax = self.getSyntaxByFilePath(filePath)
        if syntax == 'C++':
            result = re.findall(r'#\s*include\s*\"([^\"]+)\"', 
                    fileContent)


        else:
            return []



        return result






    def getFunctionsFromContent(self, filePath, fileContent):
        '''
        return all functions like (type, func_name, parameters)
        or (type, func_name, [param1, param2, param3])
        '''
        syntax = self.getSyntaxByFilePath(filePath)
        if syntax == 'C++':
            result = re.findall(r'(\w+)\**\s+(?:\w+\s+)*\**\s*(?:\w+\:\:)?(\w+)\s*\(([^\)]*)\)', 
                fileContent)



        elif syntax == 'JavaScript':
            # funções do tipo func_name = function () {}
            result = re.findall(r'(\w+)\s+=\s+function\s*\(([^\)]*)\)', 
                fileContent)

            # funções do tipo function func_name() {}
            result += re.findall(r'function\s+(\w+)\s*\(([^\)]*)\)', 
                fileContent)



            # força o tipo (type, func_name, parameters)
            # se func_name for diferente de __init__, por exemplo
            result = [(None, x[0], x[1]) for x in result]




        elif syntax == 'Java':
            result = re.findall(r'\s*(?:protected|private|public)\s+(\w+\s+)*(\w+)\(([^\)]*)\)', 
                fileContent)







        elif syntax == 'Python':
            result = re.findall(r'\bdef\s+(\w+)\(([^\)]*)\)\:', 
                fileContent)


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








    def getImportantWordsFromContent(self, filePath, fileContent):
        '''
        return important words
        ['word1', 'word2', 'word3', ...]
        '''
        syntax = self.getSyntaxByFilePath(filePath)
        if syntax == 'C++':
            #adicionando palavras, tipo #define word # adding words like #define word
            result = re.findall(r'\#\s*define\s+(\w+)', 
                    fileContent)
            #adicionando palavras do tipo typedef word snippet; #adding words like typedef word
            result += re.findall(r'typedef(?:\s+\w+)+\s+(\w+)\s*;', 
                    fileContent)



        elif syntax == 'HTML':
            classesString = re.findall(r'class="(.*?)"', fileContent)
            classes = sum([re.split(r'\s+', x) for x in classesString], [])
            ids = re.findall(r'id="(.*?)"', fileContent)

            return set(classes+ids)



        elif syntax == 'JSON':
            # confere todas as aspas com apenas uma palavra
            result = re.findall(r'"(\S+)"', 
                    fileContent)



        else:
            return []


        return result
