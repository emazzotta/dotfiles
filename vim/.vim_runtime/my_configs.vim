set clipboard=unnamed
set autoindent
set autoread
set cindent
set expandtab
set foldlevelstart=3
set mouse=n
set number
set relativenumber
set rtp+=/usr/local/bin/fzf
set smartindent
set smarttab
set tabstop=4
set shiftwidth=4
autocmd FileType javascript setlocal shiftwidth=2 tabstop=2
autocmd FileType json setlocal shiftwidth=2 tabstop=2
autocmd FileType html setlocal shiftwidth=2 tabstop=2
autocmd FileType yaml setlocal shiftwidth=2 tabstop=2
set ttymouse=xterm2
retab

set statusline+=%#warningmsg#
set statusline+=%{SyntasticStatuslineFlag()}
set statusline+=%*
let g:syntastic_always_populate_loc_list = 1
let g:syntastic_auto_loc_list = 1
let g:syntastic_check_on_open = 1
let g:syntastic_check_on_wq = 0
let g:AutoPairsShortcutToggle = 0
"let g:syntastic_javascript_checkers = ['eslint']
"let g:syntastic_javascript_eslint_exe = 'yarn lint --'

" When Tmux 'focus-events' option is on, Tmux will send <Esc>[O when the
" window loses focus and <Esc>[I when it gains focus.
exec "set <F24>=\<Esc>[O"
exec "set <F25>=\<Esc>[I"

nmap k gk
nmap j gj
nmap <Up> gk
nmap <Down> gj
nmap \w :setlocal wrap!<cr>:setlocal wrap?<cr>
nmap <silent> <leader>i :set paste <bar> :startinsert<cr>

map <leader>bn :bn<cr>
map <leader>bp :bp<cr>
map <leader>nn :NERDTreeToggle<cr>
map <leader>n :NERDTreeFocus<cr>
map <D-c> :w !pbcopy<cr>
map <D-v> :r !pbpaste<cr>
map <leader>vp :VimuxPromptCommand<cr>
map <leader>vl :VimuxRunLastCommand<cr>
map <leader>vc :VimuxCloseRunner<cr>

noremap <leader>s :SyntasticCheck<cr>
noremap <leader>st :SyntasticToggleMode<cr>
nnoremap <leader>as :let g:toggle_autosave = !get(g:, 'toggle_autosave', 0)<cr> <bar> :echo "Autosave:" g:toggle_autosave?"on":"off"<cr>
nnoremap <leader>p :CtrlPTag<cr>

autocmd FileType python map <buffer> <F7> :call Flake8()<cr>
autocmd TextChanged,TextChangedI <buffer> if get(g:, 'toggle_autosave', 1)|silent! wall|endif

let g:airline_powerline_fonts = 1
let g:toggle_autosave = 0
let g:NERDTreeWinPos = "left"
let g:user_emmet_leader_key='<tab>'
let g:ycm_server_python_interpreter = '/usr/local/bin/python3'

