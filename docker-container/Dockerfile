FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive TZ=Etc/UTC HOME=/root LANG=en_US.UTF-8 LC_ALL=en_US.UTF-8

RUN apt-get update && apt-get install -y --no-install-recommends \
  bash zsh git stow vim curl wget ca-certificates openssh-client less locales nodejs npm zip unzip \
  && sed -i 's/# en_US.UTF-8/en_US.UTF-8/' /etc/locale.gen && locale-gen \
  && rm -rf /var/lib/apt/lists/*

COPY /dotfiles /root/dotfiles

WORKDIR /root/dotfiles
RUN ./setup

WORKDIR /workspace

RUN apt-get update && apt-get install -y --no-install-recommends \
  neovim tmux gnupg gnupg2 \
  build-essential g++ gcc make pkg-config software-properties-common apt-transport-https lsb-release \
  ffmpeg flac fzf gh git-lfs subversion git-svn graphviz htop icdiff id3v2 imagemagick jq krb5-user \
  lftp exiftool ghostscript libavif-bin mycli maven nmap nsis openconnect openvpn \
  pandoc pdfgrep perl poppler-utils potrace pv python3 python3-pip python3-venv virtualenv rclone ruby-full \
  sloccount socat sox speedtest-cli silversearcher-ag tree watch xz-utils ripgrep lsd \
  dnsutils net-tools iproute2 iputils-ping \
  && rm -rf /var/lib/apt/lists/*

CMD ["/bin/bash"]
