### test script

1. sudo ./setup-netns.sh
  - configure network namespaces for test
2. sudo tmux new-session \; source-file start-ameshes-tmux
  - start amesh processes on each network namespace
3. sudo ./start-ping-check.sh
  - check ping between namespaces

netns1 and netns4 are server hosts, which have endpoints.
netns2 and netns3 are client hosts, which do not have endpoints.

