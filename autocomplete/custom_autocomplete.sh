if [ ! -z "${ZSH_VERSION}" ]; then
    autoload bashcompinit
    bashcompinit
fi
_agrep()
{
  _agrep_commands=$(ls ${CUSTOM_BIN_DIR})
  _agrep_commands+=$(grep -Eo '^(alias ).*' ${HOME}/.bashrc | sed 's/=.*$//g' | sed 's/alias //g')
  _agrep_commands+=$(grep -Eo '^(export ).*' ${HOME}/.bashrc | sed 's/=.*$//g' | sed 's/export //g')
  local cur prev
  COMPREPLY=()
  cur="${COMP_WORDS[COMP_CWORD]}"
  COMPREPLY=($(compgen -W "${_agrep_commands}" -- ${cur}))
  return 0
}
_ef()
{
  _ef_commands=$(ls ${CUSTOM_BIN_DIR})
  local cur prev
  COMPREPLY=()
  cur="${COMP_WORDS[COMP_CWORD]}"
  COMPREPLY=($(compgen -W "${_ef_commands}" -- ${cur}))
  return 0
}
complete -o nospace -F _agrep agrep
complete -o nospace -F _ef ef
