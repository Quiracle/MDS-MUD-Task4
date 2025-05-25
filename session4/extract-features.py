#! /usr/bin/python3

import sys
from os import listdir

from xml.dom.minidom import parse

from deptree import *
#import patterns


## ------------------- 
## -- Convert a pair of drugs and their context in a feature vector

def extract_features(tree, entities, e1, e2) :
   VERB_LISTS = {
    'advise': {'recommend', 'advise', 'warn', 'suggest'},
    'effect': {'increase', 'decrease', 'reduce', 'inhibit', 'enhance', 'stimulate'},
    'int': {'interact', 'affect', 'modify', 'alter'},
    'mechanism': {'metabolize', 'bind', 'absorb', 'transport', 'eliminate'},
   }

   feats = set()

   # get head token for each gold entity
   tkE1 = tree.get_fragment_head(entities[e1]['start'],entities[e1]['end'])
   tkE2 = tree.get_fragment_head(entities[e2]['start'],entities[e2]['end'])

   if tkE1 is  None or tkE2 is None:
      return set()  # no valid head token, skip this pair
# === Basic Features ===
   wordE1 = tree.get_word(tkE1)
   lemmaE1 = tree.get_lemma(tkE1).lower()
   tagE1 = tree.get_tag(tkE1)
   wordE2 = tree.get_word(tkE2)
   lemmaE2 = tree.get_lemma(tkE2).lower()
   tagE2 = tree.get_tag(tkE2)

   feats.update({
      "e1_word=" + wordE1,
      "e1_lemma=" + lemmaE1,
      "e1_pos=" + tagE1,
      "e2_word=" + wordE2,
      "e2_lemma=" + lemmaE2,
      "e2_pos=" + tagE2,
   })

   # Distance between E1 and E2
   feats.add('distance=' + str(tkE2 - tkE1 - 1))

   # features for tokens in between E1 and E2
   #for tk in range(tkE1+1, tkE2) :
   tk=tkE1+1
   try:
      while (tree.is_stopword(tk)):
         tk += 1
   except:
      return set()
   word  = tree.get_word(tk)
   lemma = tree.get_lemma(tk).lower()
   tag = tree.get_tag(tk)
   feats.add("lib=" + lemma)
   feats.add("wib=" + word)
   feats.add("lpib=" + lemma + "_" + tag)
   
   eib = False
   for tk in range(tkE1+1, tkE2) :
      if tree.is_entity(tk, entities):
         eib = True 
   
   # feature indicating the presence of an entity in between E1 and E2
   feats.add('eib='+ str(eib))

   # === Syntactic Path Features ===
   lcs = tree.get_LCS(tkE1, tkE2)
   if lcs is not None:
      path1 = tree.get_up_path(tkE1, lcs)
      path2 = tree.get_down_path(lcs, tkE2)

      path1_str = "<".join([tree.get_lemma(x) + "_" + tree.get_rel(x) for x in path1])
      path2_str = ">".join([tree.get_lemma(x) + "_" + tree.get_rel(x) for x in path2])
      lcs_str = tree.get_lemma(lcs) + "_" + tree.get_rel(lcs)

      feats.update({
            "path1=" + path1_str,
            "path2=" + path2_str,
            "path=" + path1_str + "<" + lcs_str + ">" + path2_str,
            "path_length=" + str(len(path1) + 1 + len(path2)),
            "path_up_len=" + str(len(path1)),
            "path_down_len=" + str(len(path2)),
            "lcs_pos=" + tree.get_tag(lcs),
            "lcs_lemma=" + tree.get_lemma(lcs),
            "lcs_rel=" + tree.get_rel(lcs),
      })

      # Manually compute size of subtree rooted at lcs (define here)
      def get_subtree_nodes(tree, root):
            nodes = [root]
            children = tree.get_children(root)
            for child in children:
               nodes.extend(get_subtree_nodes(tree, child))
            return nodes

      subtree_nodes = get_subtree_nodes(tree, lcs)
      feats.add("subtree_size=" + str(len(subtree_nodes)))

      path_pos_seq = "_".join([tree.get_tag(x) for x in path1 + [lcs] + path2])
      path_rel_seq = "_".join([tree.get_rel(x) for x in path1 + [lcs] + path2])
      feats.add("path_pos_seq=" + path_pos_seq)
      feats.add("path_rel_seq=" + path_rel_seq)

      if lcs is not None:
         path_nodes = path1 + [lcs] + path2
         eip = any(tree.is_entity(tk, entities) for tk in path_nodes)
         feats.add(f'eip={eip}')

      verbs_between = set()
      for tk in range(tkE1 + 1, tkE2):
         try:
            pos = tree.get_tag(tk)
            if pos.startswith('VB'):
                  lemma = tree.get_lemma(tk).lower()
                  verbs_between.add(lemma)
         except:
            continue  # handle token indices beyond the sentence

         
      for cls, verbs in VERB_LISTS.items():
         has_class_verb_between = bool(verbs_between & verbs)
         feats.add(f'{cls}_verb_between={has_class_verb_between}')


   return feats


## --------- MAIN PROGRAM ----------- 
## --
## -- Usage:  extract_features targetdir
## --
## -- Extracts feature vectors for DD interaction pairs from all XML files in target-dir
## --

# directory with files to process
datadir = sys.argv[1]

# process each file in directory
for f in listdir(datadir) :

    # parse XML file, obtaining a DOM tree
    tree = parse(datadir+"/"+f)

    # process each sentence in the file
    sentences = tree.getElementsByTagName("sentence")
    for s in sentences :
        sid = s.attributes["id"].value   # get sentence id
        stext = s.attributes["text"].value   # get sentence text
        # load sentence entities
        entities = {}
        ents = s.getElementsByTagName("entity")
        for e in ents :
           id = e.attributes["id"].value
           offs = e.attributes["charOffset"].value.split("-")           
           entities[id] = {'start': int(offs[0]), 'end': int(offs[-1])}

        # there are no entity pairs, skip sentence
        if len(entities) <= 1 : continue

        # analyze sentence
        analysis = deptree(stext)

        # for each pair in the sentence, decide whether it is DDI and its type
        pairs = s.getElementsByTagName("pair")
        for p in pairs:
            # ground truth
            ddi = p.attributes["ddi"].value
            if (ddi=="true") : dditype = p.attributes["type"].value
            else : dditype = "null"
            # target entities
            id_e1 = p.attributes["e1"].value
            id_e2 = p.attributes["e2"].value
            # feature extraction

            feats = extract_features(analysis,entities,id_e1,id_e2) 
            # resulting vector
            if len(feats) != 0:
              print(sid, id_e1, id_e2, dditype, "\t".join(feats), sep="\t")

